"""
tenant_credentials.py

Per-tenant SMTP sending credentials (Gmail address + App Password) for
mailer.py, so each scrap yard eventually sends enquiry confirmations and
staff notifications from their own inbox instead of one shared Gmail
account (EMAIL_USER/EMAIL_PASS today).

Kept in a table of its own, separate from tenant_settings/bot_settings
(which holds plain branding/contact copy an admin edits through a form) —
an app password is a real credential, not display text, so it doesn't sit
next to it unencrypted. The app password is encrypted at rest with Fernet
(symmetric, authenticated encryption) using a key that lives only in an
env var (CREDENTIALS_ENCRYPTION_KEY), never in the database or source —
so a copy of inventory.db on its own is not enough to recover a tenant's
Gmail credentials.

Not wired into any route yet — this is storage/validation infrastructure
only. mailer.py keeps using the shared EMAIL_USER/EMAIL_PASS env vars until
a later deploy adds request-time tenant resolution (g.tenant) and an admin
UI for a yard to enter their own credentials.

One-time setup per deploy environment (do this before anyone tries to save
tenant credentials — table creation works fine without it, only
set/get_email_credentials() need the key):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Put the output in Render's env vars (and local .env for dev) as
CREDENTIALS_ENCRYPTION_KEY. Losing this key makes every stored app password
unrecoverable — each tenant would need to re-enter theirs; nothing else is
affected.

Onboarding a tenant's Gmail account (give these steps to clients):
  1. The Gmail account must have 2-Step Verification turned on — Google
     does not allow App Passwords otherwise.
  2. Google Account -> Security -> 2-Step Verification -> App passwords.
  3. Create one (any name, e.g. "Cherrywood site"), Google shows a 16-letter
     code in 4 groups of 4 — that code is the App Password, NOT their normal
     Gmail login password.
  4. Enter the Gmail address and that 16-letter code here. set_email_credentials()
     does a live SMTP login against Gmail before saving, so a wrong address
     or mistyped code is rejected immediately instead of silently breaking
     enquiry emails later.
"""

import os
import re
import smtplib
import sqlite3
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_conn()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS tenant_email_credentials (
            tenant_id INTEGER PRIMARY KEY,
            email_address TEXT NOT NULL,
            encrypted_app_password TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        )''')
        conn.commit()
    finally:
        conn.close()


_init_table()


def _fernet():
    key = os.getenv('CREDENTIALS_ENCRYPTION_KEY')
    if not key:
        raise RuntimeError(
            'CREDENTIALS_ENCRYPTION_KEY is not set — cannot store or read '
            'tenant email credentials without it. Generate one with '
            '`Fernet.generate_key()` (see this module\'s docstring) and set '
            'it as an env var.'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _looks_like_app_password(cleaned_password: str) -> bool:
    """Fast, non-authoritative shape check — Gmail App Passwords are 16
    letters, shown as 4 groups of 4. This only catches obviously-wrong input
    (e.g. someone pasting their real Gmail password by mistake); the live
    SMTP login in validate_credentials() is the real check."""
    return bool(re.fullmatch(r'[a-zA-Z]{16}', cleaned_password))


def validate_credentials(email_address: str, app_password: str):
    """Attempts a real SMTP login (no email sent) so onboarding can confirm
    the address/app-password pair actually works before it's relied on for
    live enquiry notifications. Returns (True, None) or (False, reason)."""
    cleaned_password = app_password.replace(' ', '')
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(email_address, cleaned_password)
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, 'Gmail rejected that address/app password combination.'
    except Exception as e:
        return False, f'Could not verify credentials: {e}'


def set_email_credentials(tenant_id: int, email_address: str, app_password: str, skip_live_check: bool = False):
    """Encrypts and stores a tenant's sending credentials. Validates against
    Gmail over SMTP first by default (skip_live_check=True is only for
    tests/offline seeding) so a mistyped app password is caught at entry
    time, not the first time an enquiry email silently fails to send."""
    cleaned_password = app_password.replace(' ', '')
    if not _looks_like_app_password(cleaned_password):
        raise ValueError(
            "That doesn't look like a Gmail App Password (16 letters, no "
            "digits or symbols) — make sure it's an App Password, not the "
            "account's regular login password."
        )
    if not skip_live_check:
        ok, reason = validate_credentials(email_address, cleaned_password)
        if not ok:
            raise ValueError(reason)

    token = _fernet().encrypt(cleaned_password.encode()).decode()
    conn = _get_conn()
    try:
        conn.execute('''
            INSERT INTO tenant_email_credentials (tenant_id, email_address, encrypted_app_password, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                email_address = excluded.email_address,
                encrypted_app_password = excluded.encrypted_app_password,
                updated_at = excluded.updated_at
        ''', (tenant_id, email_address, token, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def get_email_credentials(tenant_id: int):
    """Returns {'email_address': ..., 'app_password': ...} decrypted, or
    None if this tenant hasn't configured their own sending account yet."""
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT email_address, encrypted_app_password FROM tenant_email_credentials WHERE tenant_id = ?',
            (tenant_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        password = _fernet().decrypt(row['encrypted_app_password'].encode()).decode()
    except InvalidToken:
        raise RuntimeError(
            f'Stored credentials for tenant {tenant_id} could not be decrypted — '
            'CREDENTIALS_ENCRYPTION_KEY may have changed since they were saved.'
        )
    return {'email_address': row['email_address'], 'app_password': password}
