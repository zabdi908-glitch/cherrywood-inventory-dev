"""
backup.py

Automatic off-instance database backups.

Render's persistent disk (confirmed attached, mounted at /data) protects
against container restarts and redeploys — but this Render plan has no
visible automatic snapshot feature. If the disk itself were ever lost,
corrupted, or accidentally deleted, there would be zero recovery path
without this.

Uses the same opportunistic-trigger pattern as data_retention.py: checked
cheaply on incoming requests, only doing real backup work once a day.
Backups are emailed as an attachment via the existing mailer.py — no new
cloud storage account needed, and email is itself a durable, off-instance
store.

Uses SQLite's built-in online backup API, which produces a safe, consistent
copy even while the source database is actively being written to by the
running app (unlike a plain file copy, which risks corruption on a live db).
"""

import os
import sqlite3
import tempfile
import time

BACKUP_INTERVAL_SECONDS = 24 * 60 * 60  # once per day
MAX_ATTACHMENT_MB = 20  # stay safely under typical ~25MB email attachment limits


def init_backup_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS backup_log (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_backup_at REAL NOT NULL
        )
    """)
    db.commit()


def _get_last_backup_time(db):
    row = db.execute("SELECT last_backup_at FROM backup_log WHERE id = 1").fetchone()
    return row["last_backup_at"] if row else None


def _set_last_backup_time(db, ts):
    db.execute("""
        INSERT INTO backup_log (id, last_backup_at) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET last_backup_at = ?
    """, (ts, ts))
    db.commit()


def create_backup_copy(source_db_path: str) -> str:
    """Uses SQLite's online backup API for a safe, consistent copy even while
    the source database is actively being written to. Returns the path to a
    temp file containing the backup — caller is responsible for deleting it."""
    fd, dest_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    source = sqlite3.connect(source_db_path)
    dest = sqlite3.connect(dest_path)
    with dest:
        source.backup(dest)
    source.close()
    dest.close()
    return dest_path


def maybe_backup(db, source_db_path: str):
    """Call once per request — cheap no-op unless a backup is actually due
    (roughly once every 24 hours, based on real traffic rather than a fixed
    clock, so it needs no separate scheduler infrastructure)."""
    init_backup_table(db)
    last = _get_last_backup_time(db)
    now = time.time()
    if last and (now - last) < BACKUP_INTERVAL_SECONDS:
        return

    backup_path = None
    try:
        import mailer

        backup_path = create_backup_copy(source_db_path)
        size_mb = os.path.getsize(backup_path) / (1024 * 1024)

        if size_mb > MAX_ATTACHMENT_MB:
            print(f"⚠️ [BACKUP] Database is {size_mb:.1f} MB — too large to email safely. "
                  f"Backup skipped; a different storage method (e.g. cloud upload) is needed now.", flush=True)
            mailer.alert_staff(
                "Database backup too large to email",
                f"The database is now {size_mb:.1f} MB, too large for a reliable email attachment. "
                f"Automatic email backups have stopped working — a different backup method is needed."
            )
            return

        sent = mailer.send_backup_email(backup_path, size_mb)
        if sent:
            _set_last_backup_time(db, now)
            print(f"💾 [BACKUP] Database backup emailed successfully ({size_mb:.2f} MB)", flush=True)
        else:
            print("⚠️ [BACKUP] Backup email failed to send — will retry on next check", flush=True)
    except Exception as e:
        print(f"❌ [BACKUP] Backup failed: {e}", flush=True)
    finally:
        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)
