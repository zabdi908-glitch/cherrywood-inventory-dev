"""
selection_resolver.py

Deterministic (no-LLM) resolution of customer selection messages. Handles:

  - Numeric list/option references: "list 2 option 1", "option 1 from list 2",
    "list one give me the engine" (implicit option when list has 1 item)
  - Category + number references: "1 from engines", "engine 1", "2 from the
    gearbox list", "take the first engine and second gearbox"
  - Superlatives: "cheapest", "second cheapest", "most expensive" — resolved
    against a named category if mentioned, else the most recently browsed list
  - Quantifiers: "add both", "all three", "give me every A4 headlight" —
    resolves to MULTIPLE items when the request is unambiguous
  - Bare affirmatives: "yes" — only when genuinely unambiguous
  - Single named references: "give me the a3 headlight" — only when exactly
    one candidate matches

Multiple items can be resolved from ONE message now (e.g. "list 1 option 2
and list 3 option 1") because resolution is deterministic — there's no LLM
index arithmetic left to get wrong, so the earlier one-item-per-turn safety
cap is no longer needed for anything this module can confidently parse.

Anything not confidently resolved returns (None, 0) and the caller falls
back to the existing LLM-tag-based flow (which still enforces one item per
turn, as a safety net for phrasing this module doesn't recognize).
"""

import re

_GENERIC_BRAND_TOKENS = {"audi", "vw", "volkswagen", "seat", "skoda"}
_MAX_ITEMS_PER_MESSAGE = 10  # sanity cap against absurd bulk requests

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_NUMBER_WORD_ALTERNATION = "|".join(sorted(_NUMBER_WORDS.keys(), key=len, reverse=True))

_TOKEN_PATTERN = re.compile(
    r'\b(list|lst|liist|option|opton|item)\s+(?:number\s+)?(\d+|' + _NUMBER_WORD_ALTERNATION + r')\b',
    re.IGNORECASE
)
_LIST_ALIASES = {"list", "lst", "liist"}

AFFIRMATIVE_ONLY = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "please", "correct", "confirm", "confirmed"}

_REMOVE_INTENT_PATTERN = re.compile(
    r"\b(remove|delete|take off|cancel|drop|don'?t want|scrap)\b", re.IGNORECASE
)


def try_remove_from_basket(basket_items: list, user_message: str):
    """Detects 'remove the gearbox' / 'cancel the headlight' style requests
    and resolves which basket item is meant.

    Baskets are small (typically 1-5 items), so matching is deliberately
    looser than the browse-list disambiguation logic: a customer naturally
    says "remove the gearbox," not "remove the DQ381 DSG gearbox" — so
    category-level matching is tried first. Only falls back to full
    distinctive-name-token matching if multiple basket items share a
    category and the category alone can't tell them apart.

    Returns (removed_item_or_None, ambiguous_count). ambiguous_count > 0
    means the request was clearly a removal intent but matched 0 or 2+
    basket items, so the caller should ask for clarification rather than
    guess or silently do nothing.
    """
    if not _REMOVE_INTENT_PATTERN.search(user_message):
        return None, 0

    msg_lower = user_message.lower()

    # Strategy 1: category-level match (the natural, common case)
    category_matches = []
    for item in basket_items:
        cat = (item.get("category") or "").strip().lower()
        if not cat:
            continue
        cat_singular = cat[:-1] if cat.endswith("s") and not cat.endswith("ss") else cat
        if cat_singular and (cat_singular in msg_lower or cat in msg_lower):
            category_matches.append(item)

    if len(category_matches) == 1:
        return category_matches[0], 0

    # Strategy 2: category alone was ambiguous (2+ items share it) or matched
    # nothing — disambiguate using tokens that actually DISTINGUISH between
    # the candidates, rather than requiring every token in each item's full
    # name (a customer saying "remove the DQ250 gearbox" won't also mention
    # "DSG," so requiring the full token set would fail here).
    search_pool = category_matches if category_matches else basket_items
    if len(search_pool) >= 2:
        token_sets = [set(_distinctive_tokens(it.get("name", ""))) for it in search_pool]
        matches = []
        for idx, item in enumerate(search_pool):
            other_tokens = set()
            for j, other_set in enumerate(token_sets):
                if j != idx:
                    other_tokens |= other_set
            unique_tokens = token_sets[idx] - other_tokens
            if unique_tokens and any(t in msg_lower for t in unique_tokens):
                matches.append(item)
        if len(matches) == 1:
            return matches[0], 0
        return None, len(matches) if len(matches) not in (0, 1) else len(search_pool)

    # Only one candidate to check against (search_pool has exactly 1 — the
    # "matched nothing at category level" case) — try full-name matching.
    for item in search_pool:
        distinctive = _distinctive_tokens(item.get("name", ""))
        if distinctive and all(t in msg_lower for t in distinctive):
            return item, 0

    return None, len(category_matches)


_SUPERLATIVE_PATTERN = re.compile(
    r'\b(?:(first|second|third|fourth|fifth)\s+)?(cheapest|most expensive|priciest|dearest)\b',
    re.IGNORECASE
)
_QUANTIFIER_PATTERN = re.compile(r'\b(both|all|every)\b', re.IGNORECASE)


def _to_number(word: str):
    word = word.lower()
    if word.isdigit():
        return int(word)
    return _NUMBER_WORDS.get(word)


def _pluralize(word: str) -> str:
    if word.endswith(("x", "s", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _build_category_index(items_by_browse_num: dict) -> dict:
    """Maps category name (singular + simple plural, lowercase) -> browse_number,
    derived from the real 'category' field on items, not guessed labels."""
    index = {}
    for bn, items in items_by_browse_num.items():
        if not items:
            continue
        cat = (items[0].get("category") or "").strip().lower()
        if not cat:
            continue
        index[cat] = bn
        if cat.endswith("s") and not cat.endswith(("ss", "xs", "zs")):
            # already looks plural-ish (e.g. a category literally stored as "brakes")
            index[cat[:-1]] = bn
        else:
            index[_pluralize(cat)] = bn
    return index


def _distinctive_tokens(name: str) -> list:
    raw = [t for t in re.findall(r'[a-zA-Z0-9]+', name.lower()) if len(t) >= 2]
    return [t for t in raw if t not in _GENERIC_BRAND_TOKENS]


def _parse_numeric_references(user_message: str, list_lengths: dict) -> list:
    """Extracts ALL (list_number, option_number) pairs from text like "list 2
    option 1" or "option 1 from list 2" (both orderings), in order. Handles
    implicit single-item lists ("list one give me the engine")."""
    tokens = _TOKEN_PATTERN.findall(user_message)
    pairs = []
    pending_list = None
    pending_option = None
    for kind, value in tokens:
        num = _to_number(value)
        if num is None:
            continue
        if kind.lower() in _LIST_ALIASES:
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


def _parse_category_references(user_message: str, category_index: dict) -> list:
    """Extracts (browse_number, item_number) pairs from category-name phrasing:
    "1 from engines", "engine 1", "2 from the gearbox list", "first engine",
    "second gearbox". Category names come from real item data, not guesswork."""
    if not category_index:
        return []
    cat_alternation = "|".join(sorted((re.escape(c) for c in category_index), key=len, reverse=True))
    pattern = re.compile(
        rf'\b(?P<num1>\d+|{_NUMBER_WORD_ALTERNATION})\s+(?:from\s+(?:the\s+)?)?(?P<cat1>{cat_alternation})\b'
        rf'|\b(?P<cat2>{cat_alternation})\s+(?P<num2>\d+|{_NUMBER_WORD_ALTERNATION})\b',
        re.IGNORECASE
    )
    pairs = []
    for m in pattern.finditer(user_message):
        if m.group("cat1"):
            num_word, cat_word = m.group("num1"), m.group("cat1")
        else:
            num_word, cat_word = m.group("num2"), m.group("cat2")
        num = _to_number(num_word)
        bn = category_index.get(cat_word.lower())
        if num is not None and bn is not None:
            pairs.append((bn, num))
    return pairs


def _parse_superlatives(user_message: str, items_by_browse_num: dict, category_index: dict) -> list:
    """Resolves "cheapest", "second cheapest", "most expensive" etc. Uses a
    named category if mentioned in the same message, otherwise defaults to
    the most recently browsed list."""
    m = _SUPERLATIVE_PATTERN.search(user_message)
    if not m:
        return []
    ordinal_word, kind = m.group(1), m.group(2).lower()
    position = _to_number(ordinal_word) if ordinal_word else 1

    target_bn = None
    msg_lower = user_message.lower()
    for cat_name, bn in category_index.items():
        if re.search(rf'\b{re.escape(cat_name)}\b', msg_lower):
            target_bn = bn
            break
    if target_bn is None:
        if not items_by_browse_num:
            return []
        target_bn = max(items_by_browse_num.keys())

    items = items_by_browse_num.get(target_bn)
    if not items or position > len(items):
        return []

    reverse = kind in ("most expensive", "priciest", "dearest")
    sorted_items = sorted(range(len(items)), key=lambda i: float(items[i].get("price", 0)), reverse=reverse)
    chosen_idx = sorted_items[position - 1]
    return [(target_bn, chosen_idx + 1)]


def _parse_quantifier_matches(user_message: str, items_by_browse_num: dict, category_index: dict) -> list:
    """Resolves "add both", "all three", "give me every A4 headlight" — can
    return MULTIPLE items. Only fires on an explicit quantifier word, so it
    never silently over-selects on an ordinary message."""
    if not _QUANTIFIER_PATTERN.search(user_message):
        return []
    msg_lower = user_message.lower()
    quantifier = _QUANTIFIER_PATTERN.search(user_message).group(1).lower()

    # Quantifier + named category ("all three gearboxes", "every headlight")
    for cat_name, bn in category_index.items():
        if re.search(rf'\b{re.escape(cat_name)}\b', msg_lower):
            items = items_by_browse_num.get(bn, [])
            if quantifier == "both" and len(items) != 2:
                continue
            if items:
                return [(bn, i + 1) for i in range(len(items))]

    # Quantifier + named item filter ("give me every A4 headlight"). Build the
    # vocabulary of real descriptive tokens from item names, so we can tell
    # genuine query terms ("a4") apart from filler words ("give", "every").
    # An item matches if ALL the query's descriptive tokens are present in
    # that item's own tokens — the reverse direction of Strategy 6's single-
    # item match, since here the message describes a CRITERION, not the
    # full name of one specific part.
    vocab = set()
    for items in items_by_browse_num.values():
        for item in items:
            vocab.update(_distinctive_tokens(item.get("name", "")))
    query_tokens = set(re.findall(r'[a-zA-Z0-9]+', msg_lower)) & vocab

    if query_tokens:
        for bn, items in items_by_browse_num.items():
            matches = []
            for idx, item in enumerate(items):
                item_tokens = set(_distinctive_tokens(item.get("name", "")))
                if query_tokens.issubset(item_tokens):
                    matches.append(idx)
            if matches and (quantifier != "both" or len(matches) == 2):
                return [(bn, i + 1) for i in matches]

    # Bare quantifier with no category/name — apply to the most recently
    # browsed list only (e.g. "add both" right after seeing a 2-item list).
    if items_by_browse_num:
        most_recent_bn = max(items_by_browse_num.keys())
        items = items_by_browse_num[most_recent_bn]
        if quantifier == "both" and len(items) == 2:
            return [(most_recent_bn, 1), (most_recent_bn, 2)]
        if quantifier in ("all", "every"):
            return [(most_recent_bn, i + 1) for i in range(len(items))]

    return []


def resolve(db, session_id: str, tracker, user_message: str):
    """
    Attempts full deterministic resolution of a customer's selection message.

    Returns (resolved_items, invalid_count):
      - resolved_items: list of resolved item dicts (each with '_list_id' set),
        possibly empty/None if nothing confidently resolved.
      - invalid_count: number of explicit references found that pointed at
        something out of range (so the caller can say "I couldn't find one
        of those" rather than silently ignoring it).
    """
    import chat_store

    browse_map = chat_store.get_browse_sequence_map(db, session_id)
    if not browse_map:
        return None, 0

    items_by_browse_num = {}
    for bn, lid in browse_map.items():
        items = tracker.get_list_items(lid)
        if items:
            items_by_browse_num[bn] = items

    if not items_by_browse_num:
        return None, 0

    list_lengths = {bn: len(items) for bn, items in items_by_browse_num.items()}
    category_index = _build_category_index(items_by_browse_num)

    def _resolve_pairs(pairs):
        resolved, invalid = [], 0
        seen = set()
        for list_num, option_num in pairs[:_MAX_ITEMS_PER_MESSAGE]:
            items = items_by_browse_num.get(list_num)
            if items and 1 <= option_num <= len(items):
                key = (list_num, option_num)
                if key in seen:
                    continue
                seen.add(key)
                item = dict(items[option_num - 1])
                item["_list_id"] = browse_map[list_num]
                resolved.append(item)
            else:
                invalid += 1
        return resolved, invalid

    # --- Strategy 1: explicit numeric references ("list 2 option 1", "list 1
    # option 2 and list 3 option 1") — now resolves ALL pairs found. ---
    numeric_pairs = _parse_numeric_references(user_message, list_lengths)
    if numeric_pairs:
        resolved, invalid = _resolve_pairs(numeric_pairs)
        for item in resolved:
            item["_resolved_by"] = "numeric"
        # Explicit references are authoritative — if none resolved, report the
        # invalid count rather than silently trying vaguer strategies on the
        # same message (which could produce an unrelated, confusing result).
        return (resolved or None), invalid

    # --- Strategy 2: category-name references ("1 from engines", "engine 1",
    # "take the first engine and second gearbox") ---
    category_pairs = _parse_category_references(user_message, category_index)
    if category_pairs:
        resolved, invalid = _resolve_pairs(category_pairs)
        for item in resolved:
            item["_resolved_by"] = "category"
        return (resolved or None), invalid

    # --- Strategy 3: superlatives ("cheapest", "second cheapest gearbox") ---
    superlative_pairs = _parse_superlatives(user_message, items_by_browse_num, category_index)
    if superlative_pairs:
        resolved, invalid = _resolve_pairs(superlative_pairs)
        for item in resolved:
            item["_resolved_by"] = "superlative"
        if resolved:
            return resolved, invalid

    # --- Strategy 4: quantifiers ("add both", "all three", "every A4 headlight") ---
    quantifier_pairs = _parse_quantifier_matches(user_message, items_by_browse_num, category_index)
    if quantifier_pairs:
        resolved, invalid = _resolve_pairs(quantifier_pairs)
        for item in resolved:
            item["_resolved_by"] = "quantifier"
        if resolved:
            return resolved, invalid

    # --- Strategy 5: bare affirmative ("yes") — only when genuinely
    # unambiguous (most recent list has exactly one item). ---
    normalized = user_message.strip().lower().strip("!.")
    if normalized in AFFIRMATIVE_ONLY:
        most_recent_bn = max(items_by_browse_num.keys())
        items = items_by_browse_num[most_recent_bn]
        if len(items) == 1:
            item = dict(items[0])
            item["_list_id"] = browse_map[most_recent_bn]
            item["_resolved_by"] = "affirmative"
            return [item], 0
        return None, 0

    # --- Strategy 6: single named reference ("give me the a3 headlight"),
    # only if unambiguous (exactly one candidate across all lists). ---
    msg_lower = user_message.lower()
    candidates = []
    for bn, items in items_by_browse_num.items():
        for idx, item in enumerate(items):
            distinctive = _distinctive_tokens(item.get("name", ""))
            if distinctive and all(t in msg_lower for t in distinctive):
                candidates.append((bn, idx, item))

    if len(candidates) == 1:
        bn, idx, item = candidates[0]
        resolved_item = dict(item)
        resolved_item["_list_id"] = browse_map[bn]
        resolved_item["_resolved_by"] = "name_match"
        return [resolved_item], 0

    return None, 0  # nothing confidently resolved — fall back to the LLM-tag flow
