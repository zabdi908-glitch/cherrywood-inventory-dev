"""
settings_store.py

Simple key-value settings store for admin-editable business info — phone
number, WhatsApp link, opening hours, and the chatbot's opening greeting.

Deliberately limited to safe, low-risk fields. Editing the actual AI system
prompt is NOT exposed here (see the production readiness plan, Tier 2.2) —
a bad edit there could break the selection logic built earlier, so that
stays developer-only for now. This lets non-developer staff update basic
business info without needing a code change or deploy.

tenant_id is optional (defaults to tenants_store.get_default_tenant_id())
on every function here, same pattern used throughout the multi-tenant
migration — this keeps every existing call site working unchanged until
each one is deliberately swapped to pass g.tenant['id'] explicitly.
"""

import os
import sqlite3

import tenants_store

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

DEFAULTS = {
    "company_phone": "07440 369576",
    "whatsapp_link": "https://wa.me/447440369576",
    "opening_hours": "Mon-Fri 09:00-17:00, Sat 09:00-13:00",
    "greeting_message": "Hi there! 👋 I can help you find parts, check prices, or take an enquiry. What can I help you with today?",
    "faq_text": "",
    # Branding/contact — injected into every template via the
    # inject_tenant_context() context processor, and threaded through the
    # confirmation/reply emails and the AI enquiry assistant's system prompt.
    "business_name": "Cherrywood Auto Parts",
    "tagline": "Birmingham-based VAG vehicle breaker. Quality used Audi, VW, SEAT and Škoda parts with UK-wide delivery and 90-day warranty.",
    "company_email": "cherryvagparts@gmail.com",
    "staff_email": "",  # empty = fall back to the STAFF_EMAIL env var
    "address_line1": "110-112 Cherrywood Road",
    "address_locality": "Bordesley Green",
    "address_region": "Birmingham",
    "postcode": "B9 4UH",
    "address_country": "GB",
    "licence_number": "102422",
    "epr_ref": "TP3398VM",
    "compliance_band": "B (100%)",
    "google_site_verification": "-Lx5gelj8gDSmTO9rFYgXnc16xOnGW0Fco-GYggZRnI",
    "hero_image_url": "/static/shutter-background.jpg",
}


def _get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    """Bootstraps bot_settings, rebuilding it onto a composite
    (tenant_id, key) primary key if it still has the original single-tenant
    shape (key TEXT PRIMARY KEY). This is the one destructive-shaped
    operation in this table's history — treated with the same discipline
    as the original tenant_id additive migration: row counts are verified
    before anything is dropped, and a mismatch aborts loudly (raises,
    which fails app startup) rather than silently proceeding. A straight
    `INSERT ... SELECT` copy with no filtering should never produce a
    different row count than its source — if it ever does, something is
    deeply wrong and needs a human before any settings functionality
    (admin panel, chat greeting, etc.) can be trusted again, so failing
    loudly at the one predictable startup point is safer than letting every
    individual settings read/write fail confusingly at runtime instead.
    """
    conn = _get_conn()
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_settings'"
        ).fetchone()

        if not exists:
            # Fresh DB — create directly with the tenant-scoped shape, no
            # rebuild needed.
            conn.execute("""
                CREATE TABLE bot_settings (
                    tenant_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (tenant_id, key)
                )
            """)
            conn.commit()
            return

        columns = [row[1] for row in conn.execute("PRAGMA table_info(bot_settings)").fetchall()]
        if 'tenant_id' in columns:
            return  # already migrated — idempotent, nothing to do

        # Old shape (key TEXT PRIMARY KEY, value TEXT). Copy into a new
        # composite-PK table first, verify the row count matches, and only
        # then drop the original — at every point up to the verified copy,
        # the original bot_settings table is untouched and still fully
        # functional under the old code path.
        default_tenant_id = tenants_store.get_default_tenant_id()
        before_count = conn.execute("SELECT COUNT(*) c FROM bot_settings").fetchone()[0]

        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings_new (
                tenant_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (tenant_id, key)
            )
        """)
        conn.execute(
            "INSERT INTO bot_settings_new (tenant_id, key, value) "
            "SELECT ?, key, value FROM bot_settings",
            (default_tenant_id,)
        )
        conn.commit()

        after_count = conn.execute("SELECT COUNT(*) c FROM bot_settings_new").fetchone()[0]
        if after_count != before_count:
            # Nothing dropped. bot_settings (original) is still intact;
            # bot_settings_new is an inert leftover for inspection.
            raise RuntimeError(
                f"bot_settings migration row count mismatch: "
                f"{before_count} before, {after_count} after copy — aborted "
                f"before dropping anything. The original bot_settings table "
                f"is untouched. Inspect bot_settings_new before retrying."
            )

        conn.execute("DROP TABLE bot_settings")
        conn.execute("ALTER TABLE bot_settings_new RENAME TO bot_settings")
        conn.commit()
        print(
            f"[MIGRATION] bot_settings rebuilt with composite (tenant_id, key) PK — "
            f"{after_count} row(s) preserved, tagged tenant_id={default_tenant_id}",
            flush=True
        )
    finally:
        conn.close()


_init_table()


def get_setting(key: str, tenant_id: int = None) -> str:
    if tenant_id is None:
        tenant_id = tenants_store.get_default_tenant_id()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM bot_settings WHERE tenant_id = ? AND key = ?",
            (tenant_id, key)
        ).fetchone()
        if row and row["value"] is not None and row["value"] != "":
            return row["value"]
        return DEFAULTS.get(key, "")
    finally:
        conn.close()


def get_all_settings(tenant_id: int = None) -> dict:
    if tenant_id is None:
        tenant_id = tenants_store.get_default_tenant_id()
    return {key: get_setting(key, tenant_id) for key in DEFAULTS}


def update_settings(updates: dict, tenant_id: int = None):
    """Only known, safe keys (from DEFAULTS) are ever written — this
    deliberately prevents arbitrary key injection from a form field."""
    if tenant_id is None:
        tenant_id = tenants_store.get_default_tenant_id()
    conn = _get_conn()
    try:
        for key, value in updates.items():
            if key not in DEFAULTS:
                continue
            conn.execute("""
                INSERT INTO bot_settings (tenant_id, key, value) VALUES (?, ?, ?)
                ON CONFLICT(tenant_id, key) DO UPDATE SET value = excluded.value
            """, (tenant_id, key, value))
        conn.commit()
    finally:
        conn.close()
