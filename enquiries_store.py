"""
enquiries_store.py

Persistent, SQLite-backed enquiry storage — replaces a MockEnquiryStore that
stored enquiries only in an in-memory Python list (self.enquiries = []).
That meant every enquiry was silently lost on every server restart or
redeploy, with zero persistence beyond whatever staff notification email
happened to be sent at the time.

This uses the same database file as everything else (mirrors app.py's
Render-vs-local path logic), so enquiries now genuinely persist across
restarts AND are covered by the same daily backup mechanism (backup.py)
as the rest of the database.

Keeps the exact same call interface as the previous mock, so nothing else
(the proxy_chat route, admin panel, etc.) needs to change:
    enquiries_store.add_enquiry(data) -> enquiry_id
    enquiries_store.update_status(enquiry_id, status, notes=None) -> bool

Also adds capabilities the mock never had, needed for GDPR compliance:
    enquiries_store.delete_enquiry(id)      — honor a deletion request
    enquiries_store.purge_old(retention_days) — automatic retention enforcement
    enquiries_store.get_all() / get_by_id() — for the admin panel
"""

import os
import sqlite3
import time
from datetime import datetime

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS enquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            email TEXT,
            vehicle TEXT,
            part TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            notes TEXT,
            created_at REAL NOT NULL
        )
    """)
    # Fields captured by the standalone /enquiry form that weren't tracked
    # before — wrapped individually so this is safe to run on every startup,
    # same pattern used for the vehicle/parts table migrations.
    for column_def in ['contact_method TEXT', 'urgency TEXT', 'vin TEXT', 'photos TEXT']:
        try:
            conn.execute(f'ALTER TABLE enquiries ADD COLUMN {column_def}')
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


class EnquiryStore:
    def __init__(self):
        _init_table()

    def add_enquiry(self, data: dict):
        conn = _get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO enquiries
                   (name, phone, email, vehicle, part, status, created_at,
                    contact_method, urgency, vin, photos)
                   VALUES (?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?)""",
                (
                    data.get('name'),
                    data.get('phone'),
                    data.get('email'),
                    data.get('vehicle'),
                    data.get('part'),
                    time.time(),
                    data.get('contact_method'),
                    data.get('urgency'),
                    data.get('vin'),
                    data.get('photos'),
                )
            )
            conn.commit()
            enquiry_id = cursor.lastrowid
            print(f"💾 Enquiry #{enquiry_id} saved to database", flush=True)
            return enquiry_id
        except Exception as e:
            print(f"❌ Failed to save enquiry: {e}", flush=True)
            return None
        finally:
            conn.close()

    def update_status(self, enquiry_id, status, notes=None):
        conn = _get_conn()
        try:
            if notes is not None:
                conn.execute(
                    "UPDATE enquiries SET status = ?, notes = ? WHERE id = ?",
                    (status, notes, enquiry_id)
                )
            else:
                conn.execute(
                    "UPDATE enquiries SET status = ? WHERE id = ?",
                    (status, enquiry_id)
                )
            conn.commit()
            updated = conn.total_changes > 0
            if updated:
                print(f"✅ Enquiry #{enquiry_id} updated to {status}", flush=True)
            return updated
        except Exception as e:
            print(f"❌ Failed to update enquiry #{enquiry_id}: {e}", flush=True)
            return False
        finally:
            conn.close()

    def get_all(self):
        """Generic accessor — kept for convenience, not called by the admin panel."""
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_enquiries(self, status_filter: str = 'All'):
        """Used by /admin/enquiries. status_filter='All' returns everything;
        any other value filters to an exact status match. Formats created_at
        as a readable date string here (rather than storing it that way),
        since the template displays it directly with no formatting of its
        own — but purge_old() still compares against the raw stored float."""
        conn = _get_conn()
        try:
            if status_filter and status_filter != 'All':
                rows = conn.execute(
                    "SELECT * FROM enquiries WHERE status = ? ORDER BY created_at DESC",
                    (status_filter,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["created_at"] = datetime.fromtimestamp(d["created_at"]).strftime("%d %b %Y, %H:%M")
                results.append(d)
            return results
        finally:
            conn.close()

    def get_counts(self):
        """Used by /admin/enquiries for the status tab counts. Always includes
        New/Contacted/Closed (even at zero) so the template never hits a
        missing key, plus 'Total' for the overall count — matching the exact
        key name enquiries_list.html expects (NOT 'All')."""
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) as c FROM enquiries GROUP BY status"
            ).fetchall()
            counts = {r['status']: r['c'] for r in rows}
            counts['Total'] = sum(counts.values())
            for s in ('New', 'Contacted', 'Closed'):
                counts.setdefault(s, 0)
            return counts
        finally:
            conn.close()

    def get_by_id(self, enquiry_id):
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM enquiries WHERE id = ?", (enquiry_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_enquiry(self, enquiry_id) -> bool:
        """For GDPR deletion requests."""
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM enquiries WHERE id = ?", (enquiry_id,))
            conn.commit()
            deleted = conn.total_changes > 0
            if deleted:
                print(f"🗑️ Enquiry #{enquiry_id} deleted (GDPR request)", flush=True)
            return deleted
        finally:
            conn.close()

    def purge_old(self, retention_days: int = 730):
        """Default 730 days (2 years), per agreed retention policy."""
        conn = _get_conn()
        try:
            cutoff = time.time() - (retention_days * 86400)
            cursor = conn.execute("DELETE FROM enquiries WHERE created_at < ?", (cutoff,))
            conn.commit()
            if cursor.rowcount:
                print(f"🧹 Purged {cursor.rowcount} enquiries older than {retention_days} days", flush=True)
            return cursor.rowcount
        finally:
            conn.close()


enquiries_store = EnquiryStore()
