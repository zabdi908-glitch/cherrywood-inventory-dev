"""
chat_store.py

Replaces the in-memory `sessions = {}` dict and the in-memory list tracker
with SQLite-backed storage, using the same DB you already use for parts
and enquiries. This means:

  - A Render restart or redeploy no longer wipes live customer conversations.
  - If you ever scale to multiple Render workers/instances, session state
    is shared correctly instead of randomly "forgetting" depending on
    which worker handles a given request.

Call chat_store.init_chat_tables(db) once per request (cheap — it's a
CREATE TABLE IF NOT EXISTS) before using anything else here.
"""

import json
import re
import time

SELECT_PATTERN = re.compile(r"\[SELECT:([A-Za-z0-9_]+):(\d+)\]")


def init_chat_tables(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id)")

    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_lists (
            list_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            label TEXT,
            items_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (session_id, list_id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_lists_session ON chat_lists(session_id, created_at)")

    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_list_counters (
            session_id TEXT PRIMARY KEY,
            counter INTEGER NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_friction (
            session_id TEXT PRIMARY KEY,
            count INTEGER NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_confirmed_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            item_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_confirmed_session ON chat_confirmed_selections(session_id)")
    db.commit()


# ---------------------------------------------------------------------------
# Confirmed selections — accumulates resolved items across the WHOLE
# conversation, not just the current turn. A customer typically selects
# item 1, then item 2, then item 3 across separate messages; by the time
# [ENQUIRY_COMPLETE] fires, that turn's reply has no [SELECT] tags in it at
# all, so relying on the current turn's resolved_items alone loses everything
# selected earlier. This table is the fix.
# ---------------------------------------------------------------------------

def add_confirmed_selections(db, session_id: str, items: list[dict]):
    now = time.time()
    for item in items:
        db.execute(
            "INSERT INTO chat_confirmed_selections (session_id, item_json, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(item), now)
        )
    db.commit()


def get_confirmed_selections(db, session_id: str) -> list[dict]:
    rows = db.execute(
        "SELECT item_json FROM chat_confirmed_selections WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    items = [json.loads(r["item_json"]) for r in rows]

    # Dedupe by OEM (the real unique identity of a part) — if the same item got
    # resolved more than once across the conversation, it should still only
    # appear once in the final enquiry/email, not inflate the total.
    seen_oems = set()
    deduped = []
    for item in items:
        oem = item.get("oem")
        key = oem if oem and oem != "N/A" else item.get("name")
        if key in seen_oems:
            continue
        seen_oems.add(key)
        deduped.append(item)
    return deduped


# ---------------------------------------------------------------------------
# Friction tracking — powers the "offer a human" escalation path. A "friction"
# turn is one where the bot couldn't help (no matching parts, had to ask for
# clarification, etc). Consecutive friction turns trigger a handoff offer;
# any genuinely helpful turn resets the counter.
# ---------------------------------------------------------------------------

def increment_friction(db, session_id: str) -> int:
    row = db.execute("SELECT count FROM chat_friction WHERE session_id = ?", (session_id,)).fetchone()
    count = (row["count"] if row else 0) + 1
    if row:
        db.execute("UPDATE chat_friction SET count = ? WHERE session_id = ?", (count, session_id))
    else:
        db.execute("INSERT INTO chat_friction (session_id, count) VALUES (?, ?)", (session_id, count))
    db.commit()
    return count


def reset_friction(db, session_id: str):
    db.execute("DELETE FROM chat_friction WHERE session_id = ?", (session_id,))
    db.commit()


# ---------------------------------------------------------------------------
# Message history (replaces the `sessions` dict)
# ---------------------------------------------------------------------------

def get_history(db, session_id: str, limit: int = 10) -> list[dict]:
    rows = db.execute(
        "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    rows = list(reversed(rows))  # chronological order for the API call
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def append_message(db, session_id: str, role: str, content: str, keep: int = 10):
    db.execute(
        "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, time.time())
    )
    # Trim old rows beyond `keep` for this session so the table doesn't grow forever.
    db.execute("""
        DELETE FROM chat_messages
        WHERE session_id = ? AND id NOT IN (
            SELECT id FROM chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?
        )
    """, (session_id, session_id, keep))
    db.commit()


def clear_session(db, session_id: str):
    """Wipes message history AND list state for a session — call this once
    an enquiry is submitted, so a follow-up message starts fresh."""
    db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_lists WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_list_counters WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_friction WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_confirmed_selections WHERE session_id = ?", (session_id,))
    db.commit()


def purge_old_sessions(db, older_than_days: int = 7):
    """Optional housekeeping — call this occasionally (e.g. from a scheduled
    Render Cron Job, or once at app startup) to stop the chat tables growing
    unbounded from abandoned sessions."""
    cutoff = time.time() - (older_than_days * 86400)
    db.execute("DELETE FROM chat_messages WHERE created_at < ?", (cutoff,))
    db.execute("DELETE FROM chat_lists WHERE created_at < ?", (cutoff,))
    db.commit()


# ---------------------------------------------------------------------------
# List tracking (SQLite-backed replacement for the earlier in-memory version)
# ---------------------------------------------------------------------------

class SessionListTracker:
    def __init__(self, db, session_id: str):
        self.db = db
        self.session_id = session_id

    def _next_list_id(self) -> str:
        row = self.db.execute(
            "SELECT counter FROM chat_list_counters WHERE session_id = ?",
            (self.session_id,)
        ).fetchone()
        counter = (row["counter"] if row else 0) + 1
        if row:
            self.db.execute(
                "UPDATE chat_list_counters SET counter = ? WHERE session_id = ?",
                (counter, self.session_id)
            )
        else:
            self.db.execute(
                "INSERT INTO chat_list_counters (session_id, counter) VALUES (?, ?)",
                (self.session_id, counter)
            )
        return f"L{counter}"

    def register_list(self, label: str, items: list[dict]) -> str:
        list_id = self._next_list_id()
        self.db.execute(
            "INSERT INTO chat_lists (list_id, session_id, label, items_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (list_id, self.session_id, label, json.dumps(items), time.time())
        )
        self.db.commit()
        return list_id

    def _recent_lists(self, max_lists: int = 4):
        rows = self.db.execute(
            "SELECT list_id, label, items_json FROM chat_lists WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.session_id, max_lists)
        ).fetchall()
        return list(reversed(rows))  # oldest-first for display

    def build_reference_block(self, max_lists: int = 4) -> str:
        recent = self._recent_lists(max_lists)
        if not recent:
            return "No lists have been shown yet."
        lines = ["Lists shown so far this conversation (use ONLY to map customer references to a SELECT tag):"]
        for row in recent:
            items = json.loads(row["items_json"])
            lines.append(f"\n{row['list_id']} — \"{row['label']}\":")
            for i, item in enumerate(items, start=1):
                lines.append(f"  {i}. {item['name']}")
        return "\n".join(lines)

    def _get_list_items(self, list_id: str):
        row = self.db.execute(
            "SELECT items_json FROM chat_lists WHERE session_id = ? AND list_id = ?",
            (self.session_id, list_id)
        ).fetchone()
        return json.loads(row["items_json"]) if row else None

    def resolve_selections(self, llm_text: str) -> list[dict]:
        resolved = []
        for list_id, item_num in SELECT_PATTERN.findall(llm_text):
            items = self._get_list_items(list_id)
            if not items:
                continue
            idx = int(item_num) - 1
            if 0 <= idx < len(items):
                item = dict(items[idx])
                item["_list_id"] = list_id
                resolved.append(item)
        return resolved

    def has_unresolvable_tags(self, llm_text: str) -> bool:
        for list_id, item_num in SELECT_PATTERN.findall(llm_text):
            items = self._get_list_items(list_id)
            if not items or not (0 <= int(item_num) - 1 < len(items)):
                return True
        return False

    @staticmethod
    def strip_select_tags(text: str) -> str:
        return SELECT_PATTERN.sub("", text).strip()

    def clear(self):
        clear_session(self.db, self.session_id)
