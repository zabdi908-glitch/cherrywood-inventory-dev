"""
vehicle_photos.py
Multi-photo support for vehicles, mirroring the part_photos system already
built for parts. Each function takes a raw sqlite3 connection (matching how
vehicle routes already work directly with get_db(), rather than an agent
class like parts has).

ensure_table() is called defensively at the start of every function here,
rather than relying on knowing exactly where app.py's other CREATE TABLE
statements live — CREATE TABLE IF NOT EXISTS is safe to run redundantly,
so this sidesteps that uncertainty entirely.

Not currently called from anywhere in the app (app.py inlines its own
vehicle_photos SQL directly instead) — kept tenant-aware anyway so it isn't
a landmine if it's ever wired up later.
"""

import tenants_store


def ensure_table(db):
    # tenant_id included here for a hypothetical fresh DB where this module
    # runs before app.py's init_db() — in the current app, app.py's
    # init_db() is what actually creates this table and backfills
    # tenant_id on every startup; this CREATE is a no-op against it.
    db.execute('''CREATE TABLE IF NOT EXISTS vehicle_photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehicle_id INTEGER,
        photo_url TEXT,
        photo_order INTEGER DEFAULT 0,
        tenant_id INTEGER,
        FOREIGN KEY (vehicle_id) REFERENCES vehicle(id) ON DELETE CASCADE
    )''')


def add_photo(db, vehicle_id, photo_url, order=0, tenant_id=None):
    ensure_table(db)
    if tenant_id is None:
        tenant_id = tenants_store.get_default_tenant_id()
    db.execute(
        'INSERT INTO vehicle_photos (vehicle_id, photo_url, photo_order, tenant_id) VALUES (?, ?, ?, ?)',
        (vehicle_id, photo_url, order, tenant_id)
    )
    db.commit()


def get_photos(db, vehicle_id):
    ensure_table(db)
    rows = db.execute(
        'SELECT * FROM vehicle_photos WHERE vehicle_id = ? ORDER BY photo_order',
        (vehicle_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_photo(db, photo_id, tenant_id=None):
    ensure_table(db)
    if tenant_id is None:
        tenant_id = tenants_store.get_default_tenant_id()
    # Return the photo_url before deleting, so the caller can also remove
    # the actual file from disk
    row = db.execute('SELECT photo_url FROM vehicle_photos WHERE id = ?', (photo_id,)).fetchone()
    photo_url = row['photo_url'] if row else None
    db.execute('DELETE FROM vehicle_photos WHERE id = ? AND tenant_id = ?', (photo_id, tenant_id))
    db.commit()
    return photo_url
