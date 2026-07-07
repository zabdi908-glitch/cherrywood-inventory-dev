wsgi_app = "app:app"

# Default gunicorn timeout is 30 seconds — too short for photo uploads,
# especially multiple HEIC photos in one batch (HEIC decoding is
# significantly heavier than regular JPEG). A slow upload was hitting this
# default and getting killed mid-request, which crashed the entire worker
# process and briefly took the whole site down (single-worker setup, by
# design, since SQLite doesn't handle concurrent workers safely).
#
# This is a safety net on top of the resize fix in the upload route
# (which should make uploads genuinely fast, not just avoid this timeout)
# — both together should prevent a repeat of the July 7 2026 crash.
timeout = 120
