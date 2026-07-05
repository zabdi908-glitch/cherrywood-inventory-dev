"""
contact_parser.py

Deterministic (no-LLM) extraction and validation of contact details from
free text. Same principle as selection_resolver.py: relying on an LLM to
reliably extract structured fields (name/phone/email) from natural language
is unnecessary and error-prone when a few regexes do the job precisely and
consistently.

Handles messages like:
    "Zaki 096458384 zabdi4549@gmail.com"
    "My name is Zaki. My number is 096458384. Email is zabdi4549@gmail.com"
    "I'm Zaki, 096458384, zabdi4549@gmail.com"

Fields are extracted independently — a message can supply just one field,
two, or all three. This lets the caller accumulate details across multiple
messages (see chat_store.update_contact_progress) without re-asking for
fields already successfully provided, and without rejecting an entire
submission just because one field looks wrong.
"""

import re

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')

# Deliberately permissive on FORMAT — plausibility validation happens separately
# in _normalize_phone — so we don't miss real numbers written in unusual ways
# (spaces, hyphens, leading +). Minimum length is low (3 digits total) so that
# short/invalid attempts ("12345") get extracted and flagged as invalid rather
# than silently absorbed into the name field.
PHONE_PATTERN = re.compile(r'(\+?\d[\d\s\-]{1,}\d)')

_FILLER_PHRASES = [
    "my name is", "my name's", "name is", "name:", "i am", "i'm", "im ",
    "my number is", "my number's", "number is", "phone is", "phone number is", "phone:",
    "my email is", "email is", "email:", "you can reach me at", "contact me at",
    "here is", "here's", "and my", " and ",
]


def _normalize_phone(raw: str):
    """Strips spaces/hyphens and checks the digit count falls in a plausible
    range (7-15 digits) covering UK, Irish, and other common international
    formats — deliberately lenient rather than requiring one specific
    country's format, since rejecting a real number for not matching an
    overly strict pattern is worse than accepting a slightly unusual one."""
    cleaned = re.sub(r'[\s\-]', '', raw)
    if not re.fullmatch(r'\+?\d+', cleaned):
        return None
    digit_count = len(cleaned.lstrip('+'))
    if 7 <= digit_count <= 15:
        return cleaned
    return None


def extract_contact_info(message: str) -> dict:
    """
    Returns:
        {
            'name': str | None,
            'phone': str | None,        # normalized, only set if plausible
            'email': str | None,
            'phone_raw': str | None,    # whatever was found, even if invalid
            'phone_valid': bool | None, # None = no phone-like text found at all
        }
    """
    remaining = message

    email_match = EMAIL_PATTERN.search(message)
    email = email_match.group(0) if email_match else None
    if email_match:
        remaining = remaining.replace(email_match.group(0), " ")

    phone_raw = None
    phone = None
    phone_valid = False
    phone_match = PHONE_PATTERN.search(remaining)
    if phone_match:
        phone_raw = phone_match.group(0).strip()
        remaining = remaining.replace(phone_match.group(0), " ")
        normalized = _normalize_phone(phone_raw)
        if normalized:
            phone = normalized
            phone_valid = True

    # Strip common filler phrases before treating what's left as the name.
    name_candidate = remaining.lower()
    for phrase in _FILLER_PHRASES:
        name_candidate = name_candidate.replace(phrase, " ")
    name_candidate = re.sub(r'[.,!?;:]', ' ', name_candidate)
    name_candidate = re.sub(r'\s+', ' ', name_candidate).strip()

    name = None
    if name_candidate and len(name_candidate) <= 60:
        name = " ".join(w.capitalize() for w in name_candidate.split())

    return {
        'name': name,
        'phone': phone,
        'email': email,
        'phone_raw': phone_raw,
        'phone_valid': phone_valid if phone_raw else None,
    }
