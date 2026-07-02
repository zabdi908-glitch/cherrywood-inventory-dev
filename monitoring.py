"""
monitoring.py

Lets the route send itself an alert email when something breaks (OpenAI
down, enquiry save failed, etc.) without spamming your inbox — each
distinct alert_key only fires once per cooldown window.
"""

import time

ALERT_COOLDOWN_SECONDS = 1800  # 30 minutes between repeat alerts of the same type


def init_alert_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            alert_key TEXT PRIMARY KEY,
            last_sent REAL NOT NULL
        )
    """)
    db.commit()


def should_send_alert(db, alert_key: str, cooldown_seconds: int = ALERT_COOLDOWN_SECONDS) -> bool:
    row = db.execute("SELECT last_sent FROM alert_log WHERE alert_key = ?", (alert_key,)).fetchone()
    now = time.time()
    if row and (now - row["last_sent"]) < cooldown_seconds:
        return False
    db.execute("""
        INSERT INTO alert_log (alert_key, last_sent) VALUES (?, ?)
        ON CONFLICT(alert_key) DO UPDATE SET last_sent = ?
    """, (alert_key, now, now))
    db.commit()
    return True
