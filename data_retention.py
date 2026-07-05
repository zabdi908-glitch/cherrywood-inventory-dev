"""
data_retention.py

Basic GDPR-conscious data retention: old chat session data (messages, lists,
friction counters) gets purged automatically after a retention window, rather
than sitting in SQLite forever.

Design choice: rather than requiring a separate Render Cron Job (extra
infrastructure, another thing that can silently fail), purging is triggered
opportunistically from within normal request handling — with low enough
probability that it costs nothing on any given request, but runs often
enough across real traffic to keep the table bounded.

WHAT THIS DOES NOT COVER: the `enquiries` table (customer name/phone/email
tied to a completed enquiry) — that's business record-keeping, not
ephemeral chat state, and likely needs a longer retention period plus an
actual decision from you about how long to keep it and whether customers
can request deletion. See RETENTION_NOTES below.
"""

import random

CHAT_RETENTION_DAYS = 7          # ephemeral chat session data (messages, lists)
ENQUIRY_RETENTION_DAYS = 730     # 2 years — agreed retention for customer enquiry records
PURGE_TRIGGER_PROBABILITY = 0.02  # ~1 in 50 requests triggers a purge check


def maybe_purge(db):
    """Call this once per request (cheap no-op most of the time). Purges
    chat session data older than CHAT_RETENTION_DAYS, and enquiry records
    older than ENQUIRY_RETENTION_DAYS (2 years, per agreed policy)."""
    if random.random() > PURGE_TRIGGER_PROBABILITY:
        return
    import chat_store
    chat_store.purge_old_sessions(db, older_than_days=CHAT_RETENTION_DAYS)
    print(f"🧹 [AI] Ran scheduled chat data purge (>{CHAT_RETENTION_DAYS} days old)", flush=True)

    try:
        import enquiries_store
        purged = enquiries_store.enquiries_store.purge_old(retention_days=ENQUIRY_RETENTION_DAYS)
        if purged:
            print(f"🧹 [AI] Purged {purged} enquiries older than {ENQUIRY_RETENTION_DAYS} days (2-year retention policy)", flush=True)
    except Exception as e:
        print(f"❌ [AI] Enquiry purge failed: {e}", flush=True)


RETENTION_NOTES = """
GDPR / data retention — where things stand:

1. CHAT SESSION DATA (chat_messages, chat_lists, chat_friction, chat_confirmed_selections)
   - Auto-purged after 7 days via maybe_purge() above.

2. ENQUIRIES TABLE (name, phone, email, part requested — via enquiries_store.py)
   - Auto-purged after 730 days (2 years) via maybe_purge() above, per Zaki's decision.
   - Deletion-on-request is also supported: enquiries_store.enquiries_store.delete_enquiry(id).
   - Note: this retention purge only became meaningful once enquiries_store.py was replaced
     with a real persistent SQLite-backed store — previously it was an in-memory mock that
     lost all data on every restart, so there was nothing to purge.

3. RATE LIMIT / ALERT LOG TABLES (rate_limits, alert_log)
   - Not personal data (keyed by IP/alert type, not identity) — lower priority,
     but rate_limiter.purge_old_rate_limits() already exists if you want to wire
     it in the same opportunistic way as maybe_purge() above.

4. STILL OPEN for full UK GDPR-conscious compliance:
   - A privacy notice on the site is drafted (privacy_notice_draft.md) — needs Zaki's
     review, phone number filled in, and actual publishing on the site.
   - Consider a brief legal review once enquiry volume grows — this document gets you
     to a reasonable baseline, not a legal sign-off.
"""
