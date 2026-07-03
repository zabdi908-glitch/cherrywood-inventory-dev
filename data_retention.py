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
PURGE_TRIGGER_PROBABILITY = 0.02  # ~1 in 50 requests triggers a purge check


def maybe_purge(db):
    """Call this once per request (cheap no-op most of the time). Purges
    chat session data older than CHAT_RETENTION_DAYS."""
    if random.random() > PURGE_TRIGGER_PROBABILITY:
        return
    import chat_store
    chat_store.purge_old_sessions(db, older_than_days=CHAT_RETENTION_DAYS)
    print(f"🧹 [AI] Ran scheduled chat data purge (>{CHAT_RETENTION_DAYS} days old)", flush=True)


RETENTION_NOTES = """
GDPR / data retention — where things stand and what still needs a decision:

1. CHAT SESSION DATA (chat_messages, chat_lists, chat_friction, chat_confirmed_selections)
   - Auto-purged after 7 days via maybe_purge() above.
   - This is conversational/browsing data, not tied to a fulfilled order — 7 days is
     generous for debugging recent issues without keeping it indefinitely.

2. ENQUIRIES TABLE (name, phone, email, part requested — via enquiries_store.py)
   - NOT currently auto-purged. This is your actual business record of a customer
     enquiry/order, so a much longer retention period is normal and expected —
     but "forever" isn't a real policy. Common approaches:
       a) Keep for a fixed period after the enquiry is closed (e.g. 2 years, common
          for UK small business transaction records) then delete or anonymise.
       b) Keep indefinitely but be able to delete a specific customer's record on
          request (a legal requirement under UK GDPR if requested).
   - You (Zaki) need to decide the actual retention period — that's a business/legal
     call, not something to hardcode without your input.

3. RATE LIMIT / ALERT LOG TABLES (rate_limits, alert_log)
   - Not personal data (keyed by IP/alert type, not identity) — lower priority,
     but rate_limiter.purge_old_rate_limits() already exists if you want to wire
     it in the same opportunistic way as maybe_purge() above.

4. WHAT YOU STILL NEED FOR A BASIC UK GDPR-COMPLIANT SETUP:
   - A short privacy notice on the site (what data is collected via the chatbot,
     why, how long it's kept, who to contact to request deletion). I can draft
     this once you've decided the enquiries retention period in point 2.
   - A simple way to actually delete a specific customer's enquiry record if
     they ask — worth adding a delete_enquiry(id) function to enquiries_store.py
     if one doesn't already exist.
"""
