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
import os

import pytest

import chat_store
import rate_limiter
import selection_resolver
import contact_parser


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    chat_store.init_chat_tables(conn)
    rate_limiter.init_rate_limit_table(conn)
    yield conn
    conn.close()


@pytest.fixture
def browsed_session(db):
    """A session with engine/gearbox/lighting already browsed, matching the
    scenario that caused today's real production bugs — used by several
    test classes below."""
    sid = "test-session"
    tracker = chat_store.SessionListTracker(db, sid)

    lid1 = tracker.register_list("engine", [
        {"name": "Audi A4 B9 Engine 2.0 TDI", "price": 1450.0, "oem": "04L103351", "category": "Engine"},
    ])
    chat_store.register_browse_number(db, sid, lid1)

    lid2 = tracker.register_list("gearbox", [
        {"name": "DQ381 DSG Gearbox", "price": 950.0, "oem": "DQ381", "category": "Gearbox"},
        {"name": "DQ250 DSG Gearbox", "price": 850.0, "oem": "DQ250", "category": "Gearbox"},
    ])
    chat_store.register_browse_number(db, sid, lid2)

    lid3 = tracker.register_list("lighting", [
        {"name": "Audi A3 Headlight", "price": 185.0, "oem": "8V0941003", "category": "Lighting"},
        {"name": "Audi A4 B8 Headlight", "price": 165.0, "oem": "8K0941003", "category": "Lighting"},
        {"name": "Audi A6 C7 Headlight", "price": 200.0, "oem": "4G0941003", "category": "Lighting"},
        {"name": "Audi A4 B9 Headlight", "price": 190.0, "oem": "8W0941003", "category": "Lighting"},
        {"name": "Audi Q5 Headlight", "price": 195.0, "oem": "8R0941003", "category": "Lighting"},
    ])
    chat_store.register_browse_number(db, sid, lid3)

    return db, sid, tracker


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


# ---------------------------------------------------------------------------
# Deterministic selection resolver — the core fix from today's later session.
# Covers numeric, category-name, superlative, and quantifier strategies.
# ---------------------------------------------------------------------------

class TestDeterministicResolverNumeric:
    def test_single_list_option(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "list 2 option 1")
        assert result is not None and len(result) == 1
        assert result[0]["name"] == "DQ381 DSG Gearbox"
        assert invalid == 0

    def test_reversed_order_option_from_list(self, browsed_session):
        """Regression test: 'option 2 from list 3' (option-then-list ordering)
        was silently dropped by an earlier version of the parser."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "option 2 from list 3")
        assert result is not None and result[0]["name"] == "Audi A4 B8 Headlight"

    def test_multi_item_single_message(self, browsed_session):
        """Regression test: the original production bug — 3 items across 3
        lists in one message used to produce wrong/duplicate/hallucinated
        results. Now resolved fully deterministically, all at once."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(
            db, sid, tracker, "list 1 option 1 and list 2 option 1 and list 3 option 2"
        )
        names = {r["name"] for r in result}
        assert names == {"Audi A4 B9 Engine 2.0 TDI", "DQ381 DSG Gearbox", "Audi A4 B8 Headlight"}

    def test_out_of_range_reported_as_invalid_not_silently_dropped(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "list 1 option 2")  # engine list has only 1 item
        assert result is None
        assert invalid == 1

    def test_typo_list_variant_recognized(self, browsed_session):
        """Regression test: 'lst' (missing the 'i') used to be invisible to
        the parser entirely."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "lst 2 option 1")
        assert result is not None and result[0]["name"] == "DQ381 DSG Gearbox"


class TestDeterministicResolverCategory:
    def test_number_from_category(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "2 from gearboxes")
        assert result is not None and result[0]["name"] == "DQ250 DSG Gearbox"

    def test_category_then_number(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "engine 1")
        assert result is not None and result[0]["name"] == "Audi A4 B9 Engine 2.0 TDI"

    def test_pluralization_edge_case(self, browsed_session):
        """Regression test: naive pluralization made 'gearbox' + 's' =
        'gearboxs' instead of the real word 'gearboxes', breaking this exact
        phrase."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "add both gearboxes")
        assert result is not None and len(result) == 2


class TestDeterministicResolverSuperlatives:
    def test_cheapest_in_category(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "cheapest gearbox")
        assert result is not None and result[0]["name"] == "DQ250 DSG Gearbox"  # 850 < 950

    def test_most_expensive(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "most expensive headlight")
        assert result is not None and result[0]["name"] == "Audi A6 C7 Headlight"  # 200 is highest


class TestDeterministicResolverQuantifiers:
    def test_every_matches_only_correct_subset(self, browsed_session):
        """Regression test: 'every A4 headlight' used to match ALL 5 headlights
        instead of just the 2 that are actually A4, due to a backwards
        containment check."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "give me every A4 headlight")
        names = {r["name"] for r in result}
        assert names == {"Audi A4 B8 Headlight", "Audi A4 B9 Headlight"}


class TestDeterministicResolverNamedAndAffirmative:
    def test_named_reference_unambiguous(self, browsed_session):
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "give me the a3 headlight")
        assert result is not None and result[0]["name"] == "Audi A3 Headlight"

    def test_bare_yes_ambiguous_declines(self, browsed_session):
        """'Yes' right after a 5-item list is genuinely ambiguous — the
        resolver should decline rather than guess."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "yes")
        assert result is None

    def test_bare_yes_unambiguous_resolves(self, db):
        """'Yes' right after a SINGLE-item list is unambiguous and should resolve."""
        sid = "single-item-session"
        tracker = chat_store.SessionListTracker(db, sid)
        lid = tracker.register_list("engine", [
            {"name": "Audi A4 B9 Engine 2.0 TDI", "price": 1450.0, "oem": "04L103351", "category": "Engine"}
        ])
        chat_store.register_browse_number(db, sid, lid)
        result, invalid = selection_resolver.resolve(db, sid, tracker, "yes")
        assert result is not None and result[0]["name"] == "Audi A4 B9 Engine 2.0 TDI"

    def test_brand_word_alone_does_not_false_positive(self, browsed_session):
        """Regression test: 'audi' alone used to match against item names via
        an overly loose containment check, causing brand-new browse requests
        to be wrongly treated as ambiguous selections."""
        db, sid, tracker = browsed_session
        result, invalid = selection_resolver.resolve(db, sid, tracker, "can you add audi lighting to the enquiry")
        assert result is None


# ---------------------------------------------------------------------------
# Contact info parser — deterministic extraction of name/phone/email
# ---------------------------------------------------------------------------

class TestContactParser:
    def test_all_fields_one_message_space_separated(self):
        r = contact_parser.extract_contact_info("zaki 096458384 zabdi4549@gmail.com")
        assert r["name"] == "Zaki"
        assert r["phone"] == "096458384"
        assert r["email"] == "zabdi4549@gmail.com"
        assert r["phone_valid"] is True

    def test_natural_language_sentence(self):
        r = contact_parser.extract_contact_info(
            "My name is Zaki. My number is 096458384. Email is zabdi4549@gmail.com"
        )
        assert r["name"] == "Zaki"
        assert r["phone"] == "096458384"
        assert r["email"] == "zabdi4549@gmail.com"

    def test_comma_separated(self):
        r = contact_parser.extract_contact_info("I'm Zaki, 096458384, zabdi4549@gmail.com")
        assert r["name"] == "Zaki"
        assert r["phone"] == "096458384"

    def test_international_phone_formats(self):
        for phone in ["0871234567", "+353871234567", "07123456789"]:
            r = contact_parser.extract_contact_info(f"zaki {phone} zabdi4549@gmail.com")
            assert r["phone_valid"] is True, f"Failed for {phone!r}"

    def test_invalid_short_phone_flagged_not_dropped(self):
        """Regression test: a too-short phone attempt used to be silently
        absorbed into the name field instead of being flagged as invalid."""
        r = contact_parser.extract_contact_info("My name is Zaki, phone is 12345")
        assert r["name"] == "Zaki"  # name stays clean
        assert r["phone_raw"] == "12345"
        assert r["phone_valid"] is False  # flagged, not silently dropped

    def test_no_phone_at_all_gives_none_not_false(self):
        """phone_valid should be None (nothing found) vs False (found but
        invalid) — these mean different things to the caller."""
        r = contact_parser.extract_contact_info("zaki zabdi4549@gmail.com")
        assert r["phone_raw"] is None
        assert r["phone_valid"] is None


class TestContactProgressAccumulation:
    def test_accumulates_across_messages_without_losing_valid_fields(self, db):
        sid = "contact-test"
        # Turn 1: name + invalid phone
        e1 = contact_parser.extract_contact_info("My name is Zaki, phone is 12345")
        p1 = chat_store.update_contact_progress(db, sid, name=e1["name"], phone=e1["phone"], email=e1["email"])
        assert p1["name"] == "Zaki" and p1["phone"] is None

        # Turn 2: email only
        e2 = contact_parser.extract_contact_info("zabdi4549@gmail.com")
        p2 = chat_store.update_contact_progress(db, sid, name=e2["name"], phone=e2["phone"], email=e2["email"])
        assert p2["name"] == "Zaki" and p2["email"] == "zabdi4549@gmail.com"  # name preserved

        # Turn 3: valid phone finally arrives
        e3 = contact_parser.extract_contact_info("096458384")
        p3 = chat_store.update_contact_progress(db, sid, name=e3["name"], phone=e3["phone"], email=e3["email"])
        assert p3["name"] == "Zaki" and p3["phone"] == "096458384" and p3["email"] == "zabdi4549@gmail.com"


# ---------------------------------------------------------------------------
# Enquiries store — persistence is the whole point (was previously an
# in-memory mock that lost everything on every restart)
# ---------------------------------------------------------------------------

class TestEnquiriesStorePersistence:
    def test_enquiry_survives_fresh_connection(self, tmp_path):
        """Regression test for the biggest bug found today: enquiries used to
        live only in a Python list in memory, wiped on every restart. This
        simulates a 'restart' by opening a completely fresh connection to
        the same file."""
        import enquiries_store
        db_path = str(tmp_path / "test_enquiries.db")
        enquiries_store.DATABASE = db_path
        enquiries_store._init_table()
        store = enquiries_store.EnquiryStore()

        eid = store.add_enquiry({
            "name": "Zakaria", "phone": "07123456789", "email": "z@x.com",
            "vehicle": "Audi A4", "part": "Engine"
        })
        assert eid is not None

        # Simulate a restart: brand new store instance, same file
        store2 = enquiries_store.EnquiryStore()
        results = store2.get_all_enquiries(status_filter="All")
        assert len(results) == 1
        assert results[0]["name"] == "Zakaria"

    def test_counts_use_total_key_matching_template(self, tmp_path):
        """Regression test: get_counts() originally used key 'All' but the
        actual admin template expects 'Total' — this would have silently
        shown 0 forever instead of crashing."""
        import enquiries_store
        db_path = str(tmp_path / "test_counts.db")
        enquiries_store.DATABASE = db_path
        enquiries_store._init_table()
        store = enquiries_store.EnquiryStore()
        store.add_enquiry({"name": "A", "phone": "1", "email": "a@x.com", "vehicle": "", "part": ""})
        counts = store.get_counts()
        assert "Total" in counts
        assert counts["Total"] == 1

    def test_created_at_is_human_readable_string(self, tmp_path):
        """Regression test: created_at used to be a raw Unix timestamp float,
        displayed as an ugly number since the template has no formatting
        logic of its own."""
        import enquiries_store
        db_path = str(tmp_path / "test_date.db")
        enquiries_store.DATABASE = db_path
        enquiries_store._init_table()
        store = enquiries_store.EnquiryStore()
        store.add_enquiry({"name": "A", "phone": "1", "email": "a@x.com", "vehicle": "", "part": ""})
        result = store.get_all_enquiries(status_filter="All")[0]
        assert isinstance(result["created_at"], str)
        assert not result["created_at"].replace(".", "").isdigit()  # not a raw float


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
