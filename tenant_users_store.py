"""
tenant_users_store.py

Per-tenant admin accounts. Replaces the single shared ADMIN_PASSWORD env var
(app.py's login()) with real, tenant-bound credentials — the fix for the
"admin auth has no tenant binding" gap documented in CLAUDE.md.

Each row is scoped to a tenant_id (FK into tenants_store's tenants table),
so a username is only ever looked up within the tenant the login request
resolved to (g.tenant, from app.py's resolve_tenant Host-header match) —
there is no global username namespace to leak across tenants.

Self-initializes at import time, same pattern as tenants_store.py.

Prod cutover: seed_default_admin() backfills one row for the existing
'cherrywood' tenant, hashing whatever ADMIN_PASSWORD is currently set to,
so the live env-var login keeps working unchanged through the migration.
app.py's login() is wired to check this table first and fall back to the
old env-var check only if no row matches — the env-var branch is NOT
removed here. It stays until the new login path has been confirmed working
live in production, per explicit instruction not to retire it early.
"""

import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

import tenants_store

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')


def _get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_conn()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS tenant_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, username)
        )''')
        conn.commit()
    finally:
        conn.close()


_init_table()


def seed_default_admin():
    """One-time backfill for the existing 'cherrywood' tenant: hashes
    whatever ADMIN_PASSWORD is currently set to and inserts it as that
    tenant's 'admin' user. INSERT OR IGNORE on the (tenant_id, username)
    unique constraint means this is safe to call on every startup —
    it only ever creates the row once, and never overwrites a password
    that's since been changed through the new system.
    """
    tenant_id = tenants_store.get_default_tenant_id()
    if tenant_id is None:
        return

    admin_password = os.getenv('ADMIN_PASSWORD', 'cherrywood123')
    password_hash = generate_password_hash(admin_password)

    conn = _get_conn()
    try:
        conn.execute(
            'INSERT OR IGNORE INTO tenant_users (tenant_id, username, password_hash) VALUES (?, ?, ?)',
            (tenant_id, 'admin', password_hash)
        )
        conn.commit()
    finally:
        conn.close()


def get_by_username(tenant_id, username):
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT * FROM tenant_users WHERE tenant_id = ? AND username = ?',
            (tenant_id, username)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_login(tenant_id, username, password):
    """Returns the user dict on success, None otherwise. Looked up strictly
    within tenant_id — a username that exists for a different tenant is
    treated the same as a username that doesn't exist at all."""
    user = get_by_username(tenant_id, username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None
