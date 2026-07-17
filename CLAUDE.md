# Cherrywood Auto Parts

VAG (Audi/VW/SEAT/Škoda) specialist salvage yard site — vehicle gallery + enquiry model (not a public parts inventory).

## Stack
- Flask / Python 3.14
- SQLite (persistent disk mounted at `/data` on Render)
- Tailwind CSS (build pipeline resolved after earlier Render deploy issues — don't reintroduce untracked build steps)
- Hosted on Render, deployed from GitHub
- Repo: `zabdi908-glitch/cherrywood-inventory`

## Key features
- AI enquiry assistant using OpenAI `gpt-4o-mini`, with live inventory lookup
- Enquiries admin panel, backed by SQLite
- Auto-reply email agent for incoming enquiries
- Vehicle photo upload infrastructure

## Dev / deploy workflow
- Changes pushed to GitHub → auto-deploy on Render
- **Careful with GitHub's web editor** — it has caused auto-indent bugs in `app.py` before. Prefer local edits or Claude Code edits over the GitHub web UI for anything indentation-sensitive.
- After deploying, verify with:
  - `curl -I <url>` — check HTTP response codes
  - `sqlite3` queries in Render Shell — ground-truth DB state (don't trust the app UI alone)
  - `awk` / `sed` / `cat -A` — line-level indentation diagnosis in `app.py` when something silently breaks

## Current status
Multi-tenant migration is functionally complete on the data/rendering side (schema, write-path safety, tenant resolution, branding/config templating, read-path filtering — all done and verified). Two items remain open before a second real tenant/admin can safely go live — see "Outstanding" at the end of the Session summary below. Before this migration: pivoted from public parts inventory to a vehicle gallery/enquiry model, added vehicle photo upload infrastructure, and fixed several backend bugs.

## Session summary — multi-tenant migration
Written so a fresh session can understand where this stands without the conversation history that produced it.

**1. Schema.** `tenant_id` added (nullable, backfilled to the original `cherrywood` tenant) to every table: `vehicle`, `vehicle_photos`, `enquiries`, `parts`, `part_photos`. New `tenants` table (`tenants_store.py`) is the source of truth for tenant identity (`id`, `slug`, `hostname`, `name`). `bot_settings` (business/branding config) rebuilt from a single-tenant `key`-only primary key to a composite `(tenant_id, key)` primary key — the one genuinely destructive-shaped migration in the whole effort, done with row-count verification before/after and a hard-fail-on-mismatch guard rather than a silent best-effort copy.

**2. Write-path safety sweep.** Audited every `DELETE` / `DROP` / bulk `UPDATE` on the 5 tables above (21 locations found), fixed all to scope by `tenant_id`. Recurring pattern found and fixed repeatedly: several `INSERT` statements (`add_vehicle`, `add_enquiry`, `add_part`, part-photo upload) weren't tagging new rows with `tenant_id` at all, which would've silently broken the newly-scoped `DELETE`/`UPDATE` touching those same rows. Worst single bug found: `/admin/restore` did a completely unscoped `DELETE FROM vehicle/parts/part_photos` with zero `WHERE` clause — fixed first, in isolation, before anything else in the sweep.

**3. Tenant resolution.** `resolve_tenant()` `before_request` hook in `app.py`: Host header → `tenants.hostname` match → `?tenant=<slug>` override (gated behind `ALLOW_TENANT_OVERRIDE` env var, off by default) → `DEFAULT_TENANT_SLUG` env var fallback (currently `cherrywood`) → 404 if nothing resolves. Result stored on `g.tenant` for the rest of the request.

**4. Branding/config templating.** `settings_store.py`'s `DEFAULTS` extended with 14 branding/contact fields (business name, tagline, contact email/phone/address, licence numbers, etc.), editable via `/admin/settings`. `inject_tenant_context()` context processor injects `tenant` + `tenant_settings` into every template. `base.html` fully de-hardcoded (title, JSON-LD, nav, footer, mobile bar). Tenant identity threaded through the live AI chat system prompt (`proxy_chat()`), the enquiry WhatsApp redirect, confirmation/reply emails (`email_templates.py`, `mailer.py`, `email_reply_agent.py`), and `STAFF_EMAIL` (now `tenant_settings.staff_email`, falling back to the env var when unset).

**5. Read-path filtering.** Every `SELECT` on the 5 tables reachable from a route (34 locations: vehicle listing/search/detail, the whole `/parts*` and `/part/<slug>` surface, `/admin/enquiries`, `/api/parts-by-ids`, the AI chat's spell-correction vocabulary) scoped by `tenant_id`. Same recurring companion-`INSERT` pattern from item 2 turned up again (legacy part-photo upload) and got fixed. One unrelated regression surfaced by testing (not the migration itself): `part_public_view.html` still referenced the old `bot_settings` context variable from before item 4's rename, hard-crashing the public part page — fixed.

**Verification approach used throughout**: every phase was checked by importing the real app code into an isolated sandbox and driving it with Flask's real test client against two genuine tenants (not mocks) — real HTTP requests, real Host headers, real DB state — rather than just reading the diff. Final read-path pass: 40/40 checks passed, zero cross-tenant leakage found on any page.

### Outstanding — NOT resolved, needed before a second tenant/admin goes live
1. **Admin session has no tenant binding** — see the "MUST FIX BEFORE ONBOARDING A SECOND REAL ADMIN USER" section immediately below for full detail. One shared `ADMIN_PASSWORD`; anyone logged in can manage *any* tenant's data by visiting a different tenant's domain.
2. **Per-template SEO/branding leakage** — `base.html` is fully tenant-aware, but almost every other template (`index.html`, `about.html`, `contact.html`, admin templates, the legacy `parts_*` set) has its own separately hardcoded `<title>`, canonical link, and Open Graph tags, still referencing `cherrywoodautoparts.co.uk` regardless of which tenant is being viewed. Confirmed live. Cosmetic/SEO impact only, not a data leak — deliberately left unfixed so far (deprioritized behind the two data-safety items above).

## MUST FIX BEFORE ONBOARDING A SECOND REAL ADMIN USER
Admin auth has no tenant binding. Login is a single shared `ADMIN_PASSWORD` env var and `session['logged_in'] = True` — a boolean, not an identity. Tenant resolution (host header → `g.tenant`) determines which tenant's data a request acts on, but nothing ties an authenticated session to a specific tenant. Net effect: **anyone with the one shared admin password can manage every tenant's data**, just by visiting a different tenant's domain (or the `?tenant=` dev override) while logged in — there is no per-tenant login. This is fine only as long as a single trusted operator is the sole admin across every tenant. The moment a second yard gets their own admin user who should NOT see or edit another yard's vehicles/enquiries, this must be fixed first — move to per-tenant credentials (a `tenant_users` table or similar) and bind `session['tenant_id']` at login, checked against `g.tenant['id']` on every request.

## Next up (deferred)
- **Phase 2** — vehicle detail page gallery: lightbox, zoom, swipe
- **Phase 3** — gallery listing page redesign

## Conventions
- Zaki prefers full, copy-pasteable code blocks over partial diffs/snippets — when proposing changes, show complete file states where practical.
- Don't guess at current file contents — read the actual file before editing.
- Branding/logo direction is still unresolved — don't assume a final logo or color scheme exists yet.

## What NOT to do
- Don't touch the Tailwind build config without flagging it — it took real effort to stabilize on Render.
- Don't run destructive DB operations against `/data` without explicit confirmation.
- Don't assume GitHub web editor is safe for indentation-sensitive Python edits.
