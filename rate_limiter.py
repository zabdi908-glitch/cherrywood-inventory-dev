"""
rate_limiter.py

Simple fixed-window rate limiting backed by SQLite (same DB as everything
else), so it survives Render restarts/redeploys and works correctly even
across multiple worker processes — unlike an in-memory counter dict, which
would silently reset (and let abuse through) on every deploy.

Usage:
    from rate_limiter import is_rate_limited, get_client_ip

    ip = get_client_ip(request)
    limited, reason = is_rate_limited(db, ip=ip, session_id=session_id)
    if limited:
        return jsonify({'reply': "You're sending messages a bit fast — please wait a moment and try again."}), 429
"""

import time


def init_rate_limit_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            identifier TEXT NOT NULL,
            window_start INTEGER NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (identifier, window_start)
        )
    """)
    db.commit()


def _check_and_increment(db, identifier: str, limit: int, window_seconds: int) -> bool:
    """Returns True if this identifier has exceeded `limit` requests within
    the current `window_seconds` window. Increments the counter regardless,
    so repeated abusive requests keep counting against the limit."""
    now = int(time.time())
    window_start = now - (now % window_seconds)

    db.execute("""
        INSERT INTO rate_limits (identifier, window_start, count)
        VALUES (?, ?, 1)
        ON CONFLICT(identifier, window_start) DO UPDATE SET count = count + 1
    """, (identifier, window_start))
    db.commit()

    row = db.execute(
        "SELECT count FROM rate_limits WHERE identifier = ? AND window_start = ?",
        (identifier, window_start)
    ).fetchone()

    return (row["count"] if row else 0) > limit


def is_rate_limited(db, ip: str, session_id: str):
    """Checks a small stack of limits, tightest first, so genuine customers
    chatting normally never hit these, but scripted abuse does quickly.

    Returns (limited: bool, reason: str | None)
    """
    # Burst guard: stops rapid-fire spam from a single conversation.
    if _check_and_increment(db, f"session_burst:{session_id}", limit=8, window_seconds=15):
        return True, "burst"

    # Per-session sustained limit: generous for a real back-and-forth conversation.
    if _check_and_increment(db, f"session:{session_id}", limit=40, window_seconds=600):
        return True, "session"

    # Per-IP limit: catches abuse across multiple session IDs from the same source
    # (e.g. a script rotating sessionId to dodge the per-session limit above).
    if _check_and_increment(db, f"ip:{ip}", limit=60, window_seconds=300):
        return True, "ip"

    return False, None


def get_client_ip(request) -> str:
    """Render sits behind a proxy, so request.remote_addr is often the proxy's
    IP, not the customer's. X-Forwarded-For (set by Render) has the real one
    as the first entry in the chain."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def purge_old_rate_limits(db, older_than_seconds: int = 3600):
    """Optional housekeeping — call occasionally to stop the table growing
    unbounded. Same pattern as chat_store.purge_old_sessions."""
    cutoff = int(time.time()) - older_than_seconds
    db.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
    db.commit()
