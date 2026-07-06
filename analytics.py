"""
analytics.py

MVP analytics built primarily from data already being logged elsewhere
(chat_messages, chat_lists, enquiries) — no new AI calls, no new
customer-facing behavior. Two things weren't previously recorded anywhere
in a queryable form (failed searches, escalation offers), so a small event
log table covers those specifically.
"""

import time
import json

_EVENTS_TABLE_READY = False


def init_analytics_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            event_type TEXT NOT NULL,
            detail TEXT,
            created_at REAL NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type, created_at)")
    db.commit()


def log_event(db, session_id: str, event_type: str, detail: str = None):
    db.execute(
        "INSERT INTO analytics_events (session_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
        (session_id, event_type, detail, time.time())
    )
    db.commit()


def get_conversation_count(db, days: int = None) -> int:
    if days:
        cutoff = time.time() - days * 86400
        row = db.execute(
            "SELECT COUNT(DISTINCT session_id) as c FROM chat_messages WHERE role='user' AND created_at >= ?",
            (cutoff,)
        ).fetchone()
    else:
        row = db.execute("SELECT COUNT(DISTINCT session_id) as c FROM chat_messages WHERE role='user'").fetchone()
    return row["c"] if row else 0


def get_conversations_per_day(db, days: int = 14) -> list:
    cutoff = time.time() - days * 86400
    rows = db.execute("""
        SELECT date(created_at, 'unixepoch') as day, COUNT(DISTINCT session_id) as c
        FROM chat_messages
        WHERE role = 'user' AND created_at >= ?
        GROUP BY day
        ORDER BY day ASC
    """, (cutoff,)).fetchall()
    return [{"day": r["day"], "count": r["c"]} for r in rows]


def get_most_searched_parts(db, limit: int = 10) -> list:
    """Aggregates item names across every list ever shown to a customer —
    an approximation of 'most requested parts' from real browsing activity."""
    rows = db.execute("SELECT items_json FROM chat_lists").fetchall()
    counts = {}
    for r in rows:
        try:
            items = json.loads(r["items_json"])
        except Exception:
            continue
        for item in items:
            name = item.get("name")
            if name:
                counts[name] = counts.get(name, 0) + 1
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"name": n, "count": c} for n, c in sorted_items]


def get_failed_searches(db, limit: int = 10) -> list:
    rows = db.execute("""
        SELECT detail, COUNT(*) as c FROM analytics_events
        WHERE event_type = 'search_failed' AND detail IS NOT NULL
        GROUP BY detail ORDER BY c DESC LIMIT ?
    """, (limit,)).fetchall()
    return [{"query": r["detail"], "count": r["c"]} for r in rows]


def get_escalation_count(db, days: int = None) -> int:
    if days:
        cutoff = time.time() - days * 86400
        row = db.execute(
            "SELECT COUNT(*) as c FROM analytics_events WHERE event_type='escalation_offered' AND created_at >= ?",
            (cutoff,)
        ).fetchone()
    else:
        row = db.execute("SELECT COUNT(*) as c FROM analytics_events WHERE event_type='escalation_offered'").fetchone()
    return row["c"] if row else 0


def get_average_conversation_length(db) -> float:
    rows = db.execute("""
        SELECT session_id, COUNT(*) as msg_count FROM chat_messages
        WHERE role = 'user' GROUP BY session_id
    """).fetchall()
    if not rows:
        return 0.0
    return round(sum(r["msg_count"] for r in rows) / len(rows), 1)


def count_recent_events(db, event_type: str, minutes: int = 60) -> int:
    """Counts events of a given type in the last N minutes — used to detect
    spikes (e.g. a sudden surge in failed searches, which could mean a real
    inventory gap or a search-logic regression worth investigating)."""
    cutoff = time.time() - (minutes * 60)
    row = db.execute(
        "SELECT COUNT(*) as c FROM analytics_events WHERE event_type = ? AND created_at >= ?",
        (event_type, cutoff)
    ).fetchone()
    return row["c"] if row else 0


def get_deterministic_resolution_rate(db, days: int = 30) -> dict:
    """What fraction of resolved selections avoided the LLM entirely —
    a direct measure of how much the deterministic resolver is actually
    carrying real traffic vs. falling back."""
    cutoff = time.time() - days * 86400
    det = db.execute(
        "SELECT COUNT(*) as c FROM analytics_events WHERE event_type='deterministic_resolved' AND created_at >= ?",
        (cutoff,)
    ).fetchone()["c"]
    llm = db.execute(
        "SELECT COUNT(*) as c FROM analytics_events WHERE event_type='llm_resolved' AND created_at >= ?",
        (cutoff,)
    ).fetchone()["c"]
    total = det + llm
    pct = round((det / total) * 100, 1) if total else None
    return {"deterministic": det, "llm_fallback": llm, "deterministic_pct": pct}


def get_summary(db, enquiries_store_obj) -> dict:
    """Pulls everything together for the /admin/analytics page.
    enquiries_store_obj should be the EnquiryStore instance itself
    (e.g. from `from enquiries_store import enquiries_store` in app.py),
    not the module."""
    total_conversations = get_conversation_count(db)
    conversations_30d = get_conversation_count(db, days=30)
    total_enquiries = enquiries_store_obj.get_counts().get("Total", 0)
    conversion_rate = round((total_enquiries / total_conversations) * 100, 1) if total_conversations else 0
    return {
        "total_conversations": total_conversations,
        "conversations_30d": conversations_30d,
        "total_enquiries": total_enquiries,
        "conversion_rate": conversion_rate,
        "avg_conversation_length": get_average_conversation_length(db),
        "escalations_30d": get_escalation_count(db, days=30),
        "most_searched_parts": get_most_searched_parts(db),
        "failed_searches": get_failed_searches(db),
        "conversations_per_day": get_conversations_per_day(db),
        "resolution_rate": get_deterministic_resolution_rate(db),
    }
