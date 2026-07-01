"""
list_tracker.py

Solves the "option 1 from the first list" hallucination problem by making
list state a real server-side data structure instead of something the LLM
has to re-derive from raw chat text.

Usage pattern (per session_id, e.g. Flask session or your existing conversation id):

    tracker = SessionListTracker(session_id)

    # Whenever you show the customer a list of parts (from your real DB query):
    list_id = tracker.register_list(label="Audi A3 Interior", items=[
        {"name": "Front Seat Left", "price": 155.00, "oem": "8V0881201A", "vehicle": "Audi A3"},
        {"name": "Glove Box Assembly", "price": 68.00, "oem": "5G2857104A", "vehicle": "Audi A3"},
    ])
    # -> "L2"

    # Build the reference block to inject into the system prompt (NOT full re-listing):
    reference_block = tracker.build_reference_block()

    # After the LLM responds, look for [SELECT:list_id:item_number] tags and resolve them
    # against REAL stored data (never trust the model's own text for name/price):
    resolved = tracker.resolve_selections(llm_response_text)
    # -> [{"name": "Glove Box Assembly", "price": 68.00, ...}, ...]
"""

import re
import time
import uuid

SELECT_PATTERN = re.compile(r"\[SELECT:([A-Za-z0-9_]+):(\d+)\]")

# In-memory store keyed by session_id. Swap for Redis/DB if you run multiple
# Render dynos/workers, since in-memory dicts don't share state across processes.
_SESSION_LISTS = {}


class SessionListTracker:
    def __init__(self, session_id: str):
        self.session_id = session_id
        _SESSION_LISTS.setdefault(session_id, {"lists": {}, "counter": 0})

    def _state(self):
        return _SESSION_LISTS[self.session_id]

    def register_list(self, label: str, items: list[dict]) -> str:
        """Call this every time you show a list of parts to the customer.
        `items` should come straight from your DB query — real data only."""
        state = self._state()
        state["counter"] += 1
        list_id = f"L{state['counter']}"
        state["lists"][list_id] = {
            "label": label,
            "items": items,
            "created_at": time.time(),
        }
        return list_id

    def build_reference_block(self, max_lists: int = 4) -> str:
        """Compact summary for the system prompt — item numbers + names only,
        no prices/OEMs, so the model has just enough to map a reference to
        a (list_id, item_number) pair without being tempted to restate details."""
        state = self._state()
        # Most recent lists first, capped so context doesn't bloat
        recent = list(state["lists"].items())[-max_lists:]
        if not recent:
            return "No lists have been shown yet."

        lines = ["Lists shown so far this conversation (use ONLY to map customer references to a SELECT tag):"]
        for list_id, entry in recent:
            lines.append(f"\n{list_id} — \"{entry['label']}\":")
            for i, item in enumerate(entry["items"], start=1):
                lines.append(f"  {i}. {item['name']}")
        return "\n".join(lines)

    def clear(self):
        """Call when an enquiry is submitted/conversation resets, to stop old
        lists bleeding into a brand new enquiry."""
        _SESSION_LISTS[self.session_id] = {"lists": {}, "counter": 0}

    def resolve_selections(self, llm_text: str) -> list[dict]:
        """Extract [SELECT:list_id:item_number] tags and resolve against
        real stored data. Returns [] if any tag references unknown data —
        treat that as a signal to ask the customer to clarify rather than
        silently dropping or guessing."""
        state = self._state()
        resolved = []
        for list_id, item_num in SELECT_PATTERN.findall(llm_text):
            entry = state["lists"].get(list_id)
            if not entry:
                continue  # unknown list_id -> caller should trigger clarification
            idx = int(item_num) - 1
            if 0 <= idx < len(entry["items"]):
                item = dict(entry["items"][idx])  # copy real data
                item["_list_id"] = list_id
                item["_list_label"] = entry["label"]
                resolved.append(item)
        return resolved

    def has_unresolvable_tags(self, llm_text: str) -> bool:
        """True if the model emitted a SELECT tag pointing at something
        that doesn't exist — use this to trigger the clarification fallback
        instead of proceeding with a partial/wrong selection."""
        state = self._state()
        for list_id, item_num in SELECT_PATTERN.findall(llm_text):
            entry = state["lists"].get(list_id)
            if not entry or not (0 <= int(item_num) - 1 < len(entry["items"])):
                return True
        return False

    def strip_select_tags(self, text: str) -> str:
        """Remove raw [SELECT:...] tags before showing text to the customer."""
        return SELECT_PATTERN.sub("", text).strip()
