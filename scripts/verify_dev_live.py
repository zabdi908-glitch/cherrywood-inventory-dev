"""
Run this on cherrywood-inventory-dev via: python3 scripts/verify_dev_live.py
Requires ADMIN_PASSWORD to be set in this shell's environment (it already
is, for the live gunicorn process — this script needs it too, to log in).

Throwaway verification script for the tenant-bound admin auth work — not
meant to live in the repo long-term, added here only so it could be
pulled onto cherrywood-inventory-dev via git instead of pasted into
Render Shell (paste kept truncating on long input).

Manages the session cookie explicitly, as a plain string, rather than via
requests.Session()'s automatic cookie jar. That jar scopes cookies by
Domain using the request's Host header (not just the connection URL) —
so once we started overriding Host per-request, the jar would silently
refuse to send a cookie set under one Host on a request using a different
Host. That's the exact same class of confound as the curl cookie-jar
issue we hit manually, just triggered by http.cookiejar's domain-matching
instead of curl's URL-based jar. Handling the cookie manually sidesteps
it entirely — the Host header override only ever affects what the SERVER
sees, never what our own client decides to send.

Each attack scenario gets its own fresh login immediately before the
attack request, so a rejection in one test can never contaminate the
next (avoids the ambiguity we hit manually, where login_required's two
rejection branches are indistinguishable from the response alone).
"""
import os
import re
import sqlite3
import sys

import requests

BASE = "http://localhost:10000"
DB_PATH = "/data/inventory.db"
CHERRYWOOD_HOST = "cherrywoodautoparts.co.uk"
THROWAWAY_HOST = "test-throwaway.example.com"
UNREGISTERED_HOST = "some-unregistered-host.example.com"

if "ADMIN_PASSWORD" not in os.environ:
    print("ERROR: ADMIN_PASSWORD is not set in this shell's environment.")
    print("This script needs it to log in as the real cherrywood admin.")
    sys.exit(1)

ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def extract_csrf(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def fresh_login(host):
    """Logs in as the real cherrywood admin, resolved via the given Host
    header. Returns (cookie_value, csrf_token, login_response) — plain
    strings, managed manually, not a requests.Session(). A fresh login
    per call means no test can inherit session state left over by a
    previous test's outcome."""
    r = requests.get(f"{BASE}/login", headers={"Host": host})
    cookie_val = r.cookies.get("session")
    csrf = extract_csrf(r.text)
    login_resp = requests.post(
        f"{BASE}/login",
        headers={"Host": host, "Cookie": f"session={cookie_val}"},
        data={"username": "admin", "password": ADMIN_PASSWORD, "csrf_token": csrf},
        allow_redirects=False,
    )
    # login() modifies the session (sets logged_in/tenant_id), so a fresh
    # Set-Cookie comes back — that's the one that actually carries the
    # authenticated state forward.
    new_cookie = login_resp.cookies.get("session") or cookie_val
    return new_cookie, csrf, login_resp


# --- Step 1: login as the real cherrywood admin ---
cookie_a, csrf_a, login_resp = fresh_login(CHERRYWOOD_HOST)
check(
    "1. Login as cherrywood admin succeeds",
    login_resp.status_code == 302 and cookie_a is not None,
    f"status={login_resp.status_code}",
)

# --- Step 2: sanity check — session works normally on tenant A ---
r = requests.get(
    f"{BASE}/admin/enquiries",
    headers={"Host": CHERRYWOOD_HOST, "Cookie": f"session={cookie_a}"},
    allow_redirects=False,
)
check("2. Session works normally on tenant A", r.status_code == 200, f"status={r.status_code}")

# --- Step 3: Host-header hop attack (fresh, isolated login) ---
cookie_hop, _, _ = fresh_login(CHERRYWOOD_HOST)
r = requests.get(
    f"{BASE}/admin/enquiries",
    headers={"Host": THROWAWAY_HOST, "Cookie": f"session={cookie_hop}"},
    allow_redirects=False,
)
check(
    "3. Host-header hop to tenant B rejected",
    r.status_code == 302 and "/login" in r.headers.get("Location", ""),
    f"status={r.status_code}, location={r.headers.get('Location')}",
)

# --- Step 4: ?tenant= override hijack attempt (fresh, isolated login) ---
cookie_override, _, _ = fresh_login(CHERRYWOOD_HOST)
r = requests.get(
    f"{BASE}/admin/enquiries?tenant=test-throwaway",
    headers={"Host": UNREGISTERED_HOST, "Cookie": f"session={cookie_override}"},
    allow_redirects=False,
)
check(
    "4. ?tenant= override hijack rejected",
    r.status_code == 302 and "/login" in r.headers.get("Location", ""),
    f"status={r.status_code}, location={r.headers.get('Location')}",
)

# --- Step 5: direct POST attack against tenant B's data (fresh, isolated login) ---
cookie_attack, csrf_attack, _ = fresh_login(CHERRYWOOD_HOST)

conn = sqlite3.connect(DB_PATH)
before_count = conn.execute("SELECT COUNT(*) FROM vehicle WHERE tenant_id = 3").fetchone()[0]
conn.close()

r = requests.post(
    f"{BASE}/add",
    headers={"Host": THROWAWAY_HOST, "Cookie": f"session={cookie_attack}"},
    data={
        "csrf_token": csrf_attack,
        "title": "ATTACK VEHICLE",
        "make": "Audi",
        "model": "A4",
        "year": "2020",
    },
    allow_redirects=False,
)
check(
    "5. Cross-tenant POST rejected",
    r.status_code == 302 and "/login" in r.headers.get("Location", ""),
    f"status={r.status_code}, location={r.headers.get('Location')}",
)

# --- Step 6: vehicle count check — confirm nothing was actually written ---
conn = sqlite3.connect(DB_PATH)
after_count = conn.execute("SELECT COUNT(*) FROM vehicle WHERE tenant_id = 3").fetchone()[0]
conn.close()
check(
    "6. Tenant B vehicle count unchanged",
    before_count == after_count,
    f"before={before_count}, after={after_count}",
)

print("\n--- summary ---")
failed = [r for r in results if r[0] == "FAIL"]
print(f"{len(results) - len(failed)}/{len(results)} passed")
if failed:
    for status, name in failed:
        print(f"FAILED: {name}")
