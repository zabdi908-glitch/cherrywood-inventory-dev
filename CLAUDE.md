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
Just completed a major overhaul: pivoted from public parts inventory to a vehicle gallery/enquiry model, added vehicle photo upload infrastructure, and fixed several backend bugs.

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
