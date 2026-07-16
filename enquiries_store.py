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

    # Multi-tenancy — additive migration only, same pattern as app.py's
    # vehicle/vehicle_photos migration. Nullable tenant_id, backfilled onto
    # the one pre-existing yard; enforcement is an application-layer concern
    # in a later deploy once query filtering ships.
    try:
        conn.execute('ALTER TABLE enquiries ADD COLUMN tenant_id INTEGER')
    except sqlite3.OperationalError:
        pass
    default_tenant_id = tenants_store.get_default_tenant_id()
    if default_tenant_id is not None:
        conn.execute(
            'UPDATE enquiries SET tenant_id = ? WHERE tenant_id IS NULL',
            (default_tenant_id,)
        )
    conn.execute('CREATE INDEX IF NOT EXISTS idx_enquiries_tenant ON enquiries(tenant_id)')

    conn.commit()
    conn.close()


class EnquiryStore:
    def __init__(self):
        _init_table()

    def add_enquiry(self, data: dict):
        conn = _get_conn()
        try:
            # No per-request tenant context yet (deferred resolution phase,
            # same situation as restore_vehicles() in app.py) — defaults to
            # the one pre-existing tenant. Tagging every new enquiry with
            # this tenant_id is what lets update_status()/delete_enquiry()'s
            # tenant-scoped WHERE clauses actually match this row later —
            # without it, admin status updates and GDPR deletions on any
            # enquiry submitted after this fix would silently affect 0 rows.
            tenant_id = tenants_store.get_default_tenant_id()
            cursor = conn.execute(
                """INSERT INTO enquiries
                   (name, phone, email, vehicle, part, status, created_at,
                    contact_method, urgency, vin, photos, tenant_id)
                   VALUES (?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?, ?)""",
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
                    tenant_id,
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

    def update_status(self, enquiry_id, status, notes=None, tenant_id=None):
        """tenant_id defaults to the one pre-existing tenant when not passed
        (no per-request tenant context exists yet — same situation as
        restore_vehicles() in app.py); pass it explicitly once a caller has
        a real g.tenant to hand over. Defensive: id is already unique, but
        this means a guessed/foreign enquiry_id can never update another
        tenant's enquiry."""
        conn = _get_conn()
        try:
            if tenant_id is None:
                tenant_id = tenants_store.get_default_tenant_id()
            if notes is not None:
                conn.execute(
                    "UPDATE enquiries SET status = ?, notes = ? WHERE id = ? AND tenant_id = ?",
                    (status, notes, enquiry_id, tenant_id)
                )
            else:
                conn.execute(
                    "UPDATE enquiries SET status = ? WHERE id = ? AND tenant_id = ?",
                    (status, enquiry_id, tenant_id)
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

    def delete_enquiry(self, enquiry_id, tenant_id=None) -> bool:
        """For GDPR deletion requests. tenant_id defaults to the one
        pre-existing tenant when not passed (no per-request tenant context
        exists yet — same situation as restore_vehicles() in app.py); pass
        it explicitly once a caller has a real g.tenant to hand over.
        Defensive: id is already unique, but this means a guessed/foreign
        enquiry_id can never delete another tenant's enquiry."""
        conn = _get_conn()
        try:
            if tenant_id is None:
                tenant_id = tenants_store.get_default_tenant_id()
            conn.execute("DELETE FROM enquiries WHERE id = ? AND tenant_id = ?", (enquiry_id, tenant_id))
            conn.commit()
            deleted = conn.total_changes > 0
            if deleted:
                print(f"🗑️ Enquiry #{enquiry_id} deleted (GDPR request)", flush=True)
            return deleted
        finally:
            conn.close()

    def purge_old(self, retention_days: int = 730):
        """Default 730 days (2 years), per agreed retention policy.

        Loops every tenant and purges each one's own old enquiries,
        rather than resolving to one "current" tenant the way
        restore_vehicles() does. This runs unattended (triggered
        opportunistically from data_retention.maybe_purge(), no per-request
        tenant context exists) — but unlike a restore, retention purging
        isn't an action performed "for" whichever tenant happens to be
        current; the policy is supposed to apply to every tenant's data
        independently. Deferring this to a single default tenant would mean
        every other tenant's old enquiries silently never get purged from
        the day they onboard — a real compliance gap, not just a stopgap
        waiting on the resolution phase. So this one doesn't need a
        g.tenant swap later; it's already correct for any number of tenants."""
        conn = _get_conn()
        try:
            cutoff = time.time() - (retention_days * 86400)
            total_purged = 0
            tenants = tenants_store.get_all()
            for tenant in tenants:
                cursor = conn.execute(
                    "DELETE FROM enquiries WHERE tenant_id = ? AND created_at < ?",
                    (tenant['id'], cutoff)
                )
                total_purged += cursor.rowcount
            conn.commit()
            if total_purged:
                print(f"🧹 Purged {total_purged} enquiries older than {retention_days} days across {len(tenants)} tenant(s)", flush=True)
            return total_purged
        finally:
            conn.close()


enquiries_store = EnquiryStore()
