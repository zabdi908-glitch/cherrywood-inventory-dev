"""
selection_resolver.py

The core insight after a long day of debugging: gpt-4o-mini is unreliable at
correctly mapping structured references like "list 2, option 1" against a
reference table it read earlier in the conversation. No amount of prompt
engineering or after-the-fact verification fully closes that gap, because
the model is doing index arithmetic it isn't built to do reliably.

This module removes the model from that step entirely for the common,
parseable cases:
  - Numeric references: "list 2 option 1", "option 2 from list 3", "list one
    give me the engine" (implicit option when the list has exactly one item)
  - Bare affirmatives: "yes" when there's exactly one item in the most
    recently browsed list
  - Named references: "give me the a3 headlight" — resolved by matching
    distinctive (non-brand) tokens against real item names, but ONLY when
    the match is unambiguous (exactly one candidate)

If none of these confidently resolve, this module returns None and the
existing LLM-tag-based flow handles it as before — this is a fast path for
the common cases, not a replacement for the whole system.
"""

import re

_GENERIC_BRAND_TOKENS = {"audi", "vw", "volkswagen", "seat", "skoda"}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

_TOKEN_PATTERN = re.compile(
    r'\b(list|option|item)\s+(?:number\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten|'
    r'first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b',
    re.IGNORECASE
)

AFFIRMATIVE_ONLY = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "correct", "confirm", "confirmed"}


def _to_number(word: str):
    word = word.lower()
    if word.isdigit():
        return int(word)
    return _NUMBER_WORDS.get(word)


def _parse_numeric_references(user_message: str, list_lengths: dict) -> list:
    """Extracts (list_number, option_number) pairs from text like "list 2
    option 1" OR "option 1 from list 2" (both orderings are common), in the
    order referenced. Handles "list one give me the engine" (no explicit
    option) by defaulting to option 1 when that list has exactly one item —
    an unambiguous case. Only the FIRST pair is used by callers, matching
    the one-item-per-turn policy."""
    tokens = _TOKEN_PATTERN.findall(user_message)
    pairs = []
    pending_list = None
    pending_option = None
    for kind, value in tokens:
        num = _to_number(value)
        if num is None:
            continue
        if kind.lower() == "list":
            if pending_option is not None:
                pairs.append((num, pending_option))
                pending_option = None
                pending_list = None
            else:
                if pending_list is not None and list_lengths.get(pending_list) == 1:
                    pairs.append((pending_list, 1))
                pending_list = num
        else:  # option / item
            if pending_list is not None:
                pairs.append((pending_list, num))
                pending_list = None
                pending_option = None
            else:
                pending_option = num
    if pending_list is not None and list_lengths.get(pending_list) == 1:
        pairs.append((pending_list, 1))
    return pairs


def resolve(db, session_id: str, tracker, user_message: str):
    """
    Attempts full deterministic resolution of a customer's selection message.
    Returns a list with exactly one resolved item dict (matching the shape
    tracker.resolve_selections() produces, with '_list_id' set), or None if
    nothing could be confidently resolved — in which case the caller should
    fall back to the existing LLM-tag-based flow.
    """
    import chat_store

    browse_map = chat_store.get_browse_sequence_map(db, session_id)
    if not browse_map:
        return None

    items_by_browse_num = {}
    for bn, lid in browse_map.items():
        items = tracker.get_list_items(lid)
        if items:
            items_by_browse_num[bn] = items

    if not items_by_browse_num:
        return None

    list_lengths = {bn: len(items) for bn, items in items_by_browse_num.items()}

    # --- Strategy 1: explicit numeric reference ("list 2 option 1") ---
    pairs = _parse_numeric_references(user_message, list_lengths)
    if pairs:
        list_num, option_num = pairs[0]  # one-item-per-turn policy — only take the first
        items = items_by_browse_num.get(list_num)
        if items and 1 <= option_num <= len(items):
            item = dict(items[option_num - 1])
            item["_list_id"] = browse_map[list_num]
            item["_resolved_by"] = "numeric"
            return [item]
        return None  # explicit but out-of-range reference — don't guess, let normal flow handle it

    # --- Strategy 2: bare affirmative ("yes") when the most recent browsed
    # list has exactly one item — otherwise it's genuinely ambiguous. ---
    normalized = user_message.strip().lower().strip("!.")
    if normalized in AFFIRMATIVE_ONLY:
        most_recent_bn = max(items_by_browse_num.keys())
        items = items_by_browse_num[most_recent_bn]
        if len(items) == 1:
            item = dict(items[0])
            item["_list_id"] = browse_map[most_recent_bn]
            item["_resolved_by"] = "affirmative"
            return [item]
        return None  # ambiguous — more than one item, "yes" alone can't disambiguate

    # --- Strategy 3: named reference ("give me the a3 headlight"), only if
    # the match is unambiguous (exactly one candidate across all lists). ---
    msg_lower = user_message.lower()
    candidates = []
    for bn, items in items_by_browse_num.items():
        for idx, item in enumerate(items):
            name = item.get("name", "")
            raw_tokens = [t for t in re.findall(r'[a-zA-Z0-9]+', name.lower()) if len(t) >= 2]
            distinctive = [t for t in raw_tokens if t not in _GENERIC_BRAND_TOKENS]
            if distinctive and all(t in msg_lower for t in distinctive):
                candidates.append((bn, idx, item))

    if len(candidates) == 1:
        bn, idx, item = candidates[0]
        resolved_item = dict(item)
        resolved_item["_list_id"] = browse_map[bn]
        resolved_item["_resolved_by"] = "name_match"
        return [resolved_item]

    return None  # zero or ambiguous matches — fall back to the LLM-tag flow
