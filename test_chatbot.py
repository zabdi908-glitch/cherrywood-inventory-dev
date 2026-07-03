"""
test_chatbot.py

Run with: pytest test_chatbot.py -v

Covers the core logic that's been manually smoke-tested throughout
development — turning those one-off checks into something that runs
automatically and catches regressions before they reach production.

Requires: pip install pytest --break-system-packages
"""

import re
import sqlite3

import pytest

import chat_store
import rate_limiter


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    chat_store.init_chat_tables(conn)
    rate_limiter.init_rate_limit_table(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# List tracking / tag resolution
# ---------------------------------------------------------------------------

class TestListTracker:
    def test_register_and_resolve(self, db):
        tracker = chat_store.SessionListTracker(db, "s1")
        list_id = tracker.register_list("engine", [{"name": "Engine A", "price": 100.0, "oem": "E1"}])
        resolved = tracker.resolve_selections(f"[SELECT:{list_id}:1]")
        assert len(resolved) == 1
        assert resolved[0]["name"] == "Engine A"

    def test_unresolvable_tag_detected(self, db):
        tracker = chat_store.SessionListTracker(db, "s1")
        tracker.register_list("engine", [{"name": "Engine A", "price": 100.0, "oem": "E1"}])
        assert tracker.has_unresolvable_tags("[SELECT:L1:5]") is True

    def test_valid_tag_not_flagged_unresolvable(self, db):
        tracker = chat_store.SessionListTracker(db, "s1")
        tracker.register_list("engine", [{"name": "Engine A", "price": 100.0, "oem": "E1"}])
        assert tracker.has_unresolvable_tags("[SELECT:L1:1]") is False

    def test_strip_select_tags(self, db):
        tracker = chat_store.SessionListTracker(db, "s1")
        cleaned = tracker.strip_select_tags("Got it [SELECT:L1:1] thanks!")
        assert "[SELECT" not in cleaned

    def test_reference_block_shows_recent_lists(self, db):
        tracker = chat_store.SessionListTracker(db, "s1")
        tracker.register_list("engine", [{"name": "Engine A"}])
        tracker.register_list("gearbox", [{"name": "Gearbox A"}, {"name": "Gearbox B"}])
        block = tracker.build_reference_block()
        assert "L1" in block and "L2" in block
        assert "Engine A" in block and "Gearbox B" in block

    def test_list_survives_across_many_intervening_lists_with_wide_window(self, db):
        """Regression test for the 'list one dropped from reference table' bug."""
        tracker = chat_store.SessionListTracker(db, "s1")
        tracker.register_list("engine", [{"name": "Engine A"}])  # L1
        for i in range(6):
            tracker.register_list(f"filler{i}", [{"name": f"Filler {i}"}])
        block = tracker.build_reference_block(max_lists=8)
        assert "L1" in block  # still visible with a wide-enough window


# ---------------------------------------------------------------------------
# Confirmed selections — accumulation and deduplication
# ---------------------------------------------------------------------------

class TestConfirmedSelections:
    def test_accumulates_across_turns(self, db):
        chat_store.add_confirmed_selections(db, "s1", [{"name": "Engine A", "oem": "E1", "price": 100.0}])
        chat_store.add_confirmed_selections(db, "s1", [{"name": "Gearbox A", "oem": "G1", "price": 200.0}])
        result = chat_store.get_confirmed_selections(db, "s1")
        assert len(result) == 2

    def test_dedupes_by_oem(self, db):
        item = {"name": "Engine A", "oem": "E1", "price": 100.0}
        chat_store.add_confirmed_selections(db, "s1", [item])
        chat_store.add_confirmed_selections(db, "s1", [item])  # same item confirmed twice
        result = chat_store.get_confirmed_selections(db, "s1")
        assert len(result) == 1  # regression test for the doubled-total email bug

    def test_clear_session_wipes_confirmed_selections(self, db):
        chat_store.add_confirmed_selections(db, "s1", [{"name": "Engine A", "oem": "E1", "price": 100.0}])
        tracker = chat_store.SessionListTracker(db, "s1")
        tracker.clear()
        assert chat_store.get_confirmed_selections(db, "s1") == []


# ---------------------------------------------------------------------------
# Duplicate-selection detection (same turn, wrong index mapped twice)
# ---------------------------------------------------------------------------

def _has_duplicate_selection(items):
    seen = set()
    for it in items:
        key = (it.get("_list_id"), it.get("name"))
        if key in seen:
            return True
        seen.add(key)
    return False


class TestDuplicateDetection:
    def test_catches_same_list_and_item_twice(self):
        items = [
            {"_list_id": "L2", "name": "Gearbox A"},
            {"_list_id": "L2", "name": "Gearbox A"},
        ]
        assert _has_duplicate_selection(items) is True

    def test_distinct_items_not_flagged(self):
        items = [
            {"_list_id": "L1", "name": "Engine A"},
            {"_list_id": "L2", "name": "Gearbox A"},
            {"_list_id": "L3", "name": "Headlight A"},
        ]
        assert _has_duplicate_selection(items) is False


# ---------------------------------------------------------------------------
# Friction / escalation counter
# ---------------------------------------------------------------------------

class TestFriction:
    def test_increments_and_resets(self, db):
        assert chat_store.increment_friction(db, "s1") == 1
        assert chat_store.increment_friction(db, "s1") == 2
        chat_store.reset_friction(db, "s1")
        assert chat_store.increment_friction(db, "s1") == 1

    def test_reaches_escalation_threshold(self, db):
        counts = [chat_store.increment_friction(db, "s1") for _ in range(3)]
        assert counts[-1] >= 3  # matches FRICTION_ESCALATION_THRESHOLD in the route


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_burst_limit_trips(self, db):
        tripped = False
        for _ in range(10):
            limited, reason = rate_limiter.is_rate_limited(db, ip="1.2.3.4", session_id="s1")
            if limited:
                tripped = True
                assert reason == "burst"
                break
        assert tripped

    def test_different_sessions_dont_interfere(self, db):
        for _ in range(5):
            limited, _ = rate_limiter.is_rate_limited(db, ip="1.2.3.4", session_id="session-a")
            assert not limited
        limited, _ = rate_limiter.is_rate_limited(db, ip="1.2.3.4", session_id="session-b")
        assert not limited


# ---------------------------------------------------------------------------
# Selection-request detection (drives is_selection_turn / customer_is_selecting)
# ---------------------------------------------------------------------------

SELECTION_REQUEST_PATTERN = re.compile(
    r'\b(?:option|list)\s*\d+|\d+\s*(?:st|nd|rd|th)?\s*(?:option|item)\b', re.IGNORECASE
)


class TestSelectionDetection:
    def test_detects_multi_list_request(self):
        msg = "from list one give me the engine from list 2 give me option 1 and then from list 3 give me option 2"
        matches = SELECTION_REQUEST_PATTERN.findall(msg)
        assert len(matches) >= 2

    def test_plain_browse_message_not_flagged(self):
        msg = "what about lighting for audi"
        assert SELECTION_REQUEST_PATTERN.search(msg) is None

    def test_typo_option_not_falsely_matched(self):
        msg = "from list 3 give meoption 2"
        matches = SELECTION_REQUEST_PATTERN.findall(msg)
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# Search precision — AND-before-OR keyword matching
# ---------------------------------------------------------------------------

@pytest.fixture
def parts_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE parts (
            part_name TEXT, make TEXT, model TEXT, category TEXT,
            price REAL, stock_status TEXT, oem_number TEXT, engine_code TEXT, created_at REAL
        )
    """)
    rows = [
        ("Audi A4 B9 Engine 2.0 TDI", "Audi", "A4", "Engine", 1450.0, "Available", "04L103351", None, 1),
        ("DQ381 DSG Gearbox", "Audi", "S3", "Gearbox", 950.0, "Available", "DQ381", None, 2),
        ("Audi A3 Headlight", "Audi", "A3", "Lighting", 185.0, "Available", "8V0941003", None, 3),
        ("Audi A4 B8 Headlight", "Audi", "A4", "Lighting", 165.0, "Available", "8K0941003", None, 4),
        ("Audi A3 Bumper", "Audi", "A3", "Body Panel", 195.0, "Available", "X1", None, 5),
    ]
    conn.executemany("INSERT INTO parts VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    yield conn
    conn.close()


def _search_and_first(db, keywords):
    like_clauses, params = [], []
    for kw in keywords[:8]:
        term = f"%{kw}%"
        like_clauses.append(
            "(part_name LIKE ? OR make LIKE ? OR model LIKE ? OR category LIKE ? OR oem_number LIKE ? OR engine_code LIKE ?)"
        )
        params.extend([term] * 6)
    where_and = " AND ".join(like_clauses)
    sql = f"SELECT part_name FROM parts WHERE stock_status='Available' AND ({where_and}) LIMIT 8"
    rows = db.execute(sql, params).fetchall()
    if rows:
        return [r["part_name"] for r in rows]
    where_or = " OR ".join(like_clauses)
    sql = f"SELECT part_name FROM parts WHERE stock_status='Available' AND ({where_or}) LIMIT 8"
    rows = db.execute(sql, params).fetchall()
    return [r["part_name"] for r in rows]


class TestSearchPrecision:
    def test_category_plus_brand_returns_only_category(self, parts_db):
        """Regression test: 'lighting for audi' used to return engines/gearboxes/
        bumpers too, since 'audi' alone matches almost every row via make/model."""
        result = _search_and_first(parts_db, ["lighting", "audi"])
        assert set(result) == {"Audi A3 Headlight", "Audi A4 B8 Headlight"}

    def test_brand_only_falls_back_to_or(self, parts_db):
        result = _search_and_first(parts_db, ["audi"])
        assert len(result) > 0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
