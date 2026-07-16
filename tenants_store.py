"""
tenants_store.py

Multi-tenant identity — the `tenants` table every other table's tenant_id
column points at. Deliberately minimal for this phase: seeds one row for
the existing production yard (Cherrywood) so every other table's tenant_id
backfill has something real to point at, plus small lookup helpers for the
host/slug resolution work that lands in a later deploy once row counts are
verified.

Mirrors the DB-path convention every other *_store.py module already uses,
and self-initializes at import time the same way settings_store.py does —
so any module that does `import tenants_store` before running its own
tenant_id backfill is guaranteed the tenants table (and the default row)
already exist, regardless of which module happens to import it first.
"""

import os
import sqlite3

if os.getenv('RENDER'):
    DATABASE = os.path.join('/data', 'inventory.db')
else:
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory.db')

# The one yard this codebase has run as up to now. Every pre-existing row in
# every table gets backfilled onto this tenant during migration, so today's
# single yard keeps working with zero behavior change until per-tenant
# resolution (host header / slug) is wired into the request path.
DEFAULT_TENANT = {
    'slug': 'cherrywood',
    'hostname': 'cherrywoodautoparts.co.uk',
    'name': 'Cherrywood Auto Parts',
}


def _get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table():
    conn = _get_conn()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            hostname TEXT UNIQUE,
            name TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute(
            'INSERT OR IGNORE INTO tenants (slug, hostname, name) VALUES (?, ?, ?)',
            (DEFAULT_TENANT['slug'], DEFAULT_TENANT['hostname'], DEFAULT_TENANT['name'])
        )
        conn.commit()
    finally:
        conn.close()


_init_table()


def get_default_tenant_id():
    """The one tenant every pre-existing row belongs to. Used by every other
    table's migration to backfill tenant_id on rows that predate tenancy."""
    conn = _get_conn()
    try:
        row = conn.execute(
            'SELECT id FROM tenants WHERE slug = ?', (DEFAULT_TENANT['slug'],)
        ).fetchone()
        return row['id'] if row else None
    finally:
        conn.close()


def get_by_id(tenant_id):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM tenants WHERE id = ?', (tenant_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_by_slug(slug):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM tenants WHERE slug = ?', (slug,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_by_hostname(hostname):
    conn = _get_conn()
    try:
        row = conn.execute('SELECT * FROM tenants WHERE hostname = ?', (hostname,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all():
    conn = _get_conn()
    try:
        rows = conn.execute('SELECT * FROM tenants ORDER BY id').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
