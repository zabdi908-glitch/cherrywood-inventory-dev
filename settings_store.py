"""
settings_store.py

Simple key-value settings store for admin-editable business info — phone
number, WhatsApp link, opening hours, and the chatbot's opening greeting.

Deliberately limited to safe, low-risk fields. Editing the actual AI system
prompt is NOT exposed here (see the production readiness plan, Tier 2.2) —
a bad edit there could break the selection logic built earlier, so that
stays developer-only for now. This lets non-developer staff update basic
business info without needing a code change or deploy.
"""

import os
import sqlite3

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
}


def _get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_table()


def get_setting(key: str) -> str:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
        if row and row["value"] is not None and row["value"] != "":
            return row["value"]
        return DEFAULTS.get(key, "")
    finally:
        conn.close()


def get_all_settings() -> dict:
    return {key: get_setting(key) for key in DEFAULTS}


def update_settings(updates: dict):
    """Only known, safe keys (from DEFAULTS) are ever written — this
    deliberately prevents arbitrary key injection from a form field."""
    conn = _get_conn()
    try:
        for key, value in updates.items():
            if key not in DEFAULTS:
                continue
            conn.execute("""
                INSERT INTO bot_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, value))
        conn.commit()
    finally:
        conn.close()
