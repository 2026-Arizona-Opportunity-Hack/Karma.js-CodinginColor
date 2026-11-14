# Phase Log

## Status board

| Phase / lane | Status (todo, running, ready-for-review, verified, cut) | Gate target | Issues | PRs | Notes |
|---|---|---|---|---|---|
| 0 | ready-for-review | Sat 17:15 | #2–#9 | #1 + 7 stacked | deploy needs human (accounts) |
| 1 | todo | Sat 19:00 | | | |
| 2A ingest/dedupe | todo | Sat 23:00 | | | |
| 2B donor screens | todo | Sat 23:00 | | | |
| 2C read API/MCP | todo | Sat 23:00 | | | |
| 3A ownership/reminders | todo | Sun 01:30 | | | |
| 3B dashboard/people | todo | Sun 01:30 | | | |
| 3C messaging backend | todo | Sun 01:30 | | | |
| 4A reports/P1 | todo | Sun 09:00 | | | |
| 4B messaging/reports UI | todo | Sun 09:00 | | | |
| 4C hardening | todo | Sun 09:00 | | | |
| 5 a11y/acceptance | todo | Sun 10:30 | | | |
| 6 docs/video/submit | todo | Sun 13:30 | | | |

## Open questions for the human / CIC
- Should initial passwords from `cli setup` force a change at first login? Not in the data model today (see Phase 0 known gaps).

## Ideas (out of scope, for later)
- `cli reset-password --email X` for when a member loses the initial password.
- Change-password page in Settings.

## Reports

### Phase 0: Foundation  (Sat 2026-11-14, 15:11–15:45 MST)
**Issues / PRs (merge in this order):** #2 → PR #1 (merged) · #3 skeleton · #4 tables (`shared`) · #5 auth · #6 CLI · #7 app shell · #8 CI + Docker · #9 deploy + costs. Branches are stacked (`phase-0/<issue>-…`), each on the previous one.
**What changed:** FastAPI backend (settings, Phoenix clock, typed errors, healthz, Alembic), people/access tables with DB-enforced governance rules, Argon2id login with hashed sessions, double-submit CSRF and audit-based rate limit, operator CLI, React shell with login and 7-section nav, CI (ruff, mypy, pytest on Postgres, tsc, eslint, prettier, build, docker build, gitleaks), single-image Dockerfile, `render.yaml`, `docs/COSTS.md`. Issue #4 was split out of the auth issue to keep PR size down.
**Gate:**
- [ ] CI green: workflow written, not yet run on GitHub (nothing pushed yet). Every step passes locally: `uv run ruff check . && uv run mypy app` → clean; `uv run pytest` → 28 passed; `npm run typecheck && npm run lint && npm run build` → clean.
- [x] `docker compose up` + `alembic upgrade head` + `cli setup` from empty: dropped and recreated `cic`, `alembic upgrade head` → "Running upgrade -> 0001", `python -m app.cli setup --file …` → two members created, passwords printed once.
- [x] Logged-out calls get 401: `test_logged_out_calls_get_401`; curl to `/api/app/auth/me` on the Docker image → 401.
- [x] Two members log in separately: `test_two_members_log_in_separately`.
- [ ] Deployed URL serves login and `/healthz`: needs the human to create Neon + Render (README "Deploy"). Locally the production image serves `/login` 200 and `/healthz` `{"status":"ok"}`.
- [x] No secrets in git: `gitleaks git --redact` (v8.24.0) → "21 commits scanned … no leaks found".
- [~] `COSTS.md` within budget with sources: Neon, Resend and Render workspace/bandwidth sourced; Render Starter dollar price could not be read from the vendor page and is marked unverified (~$7).
**How to verify (exact steps):**
1. Merge PRs in the order above (each PR's base retargets to `main` as the one below merges).
2. Locally: `docker compose up -d db`, `cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.cli setup`, `uv run pytest`.
3. `cd frontend && npm ci && npm run dev`, open http://localhost:5173 in two browsers (one private) and log in as two different members; each sees their own name. Log out works; 6 wrong passwords → "Too many attempts".
4. Follow README "Deploy", then log in on the Render URL in a private window as two members; open `/healthz`.
5. Confirm the Render Starter price on render.com/pricing and edit `docs/COSTS.md`.
**Decisions made:** D-119 to D-122.
**Known gaps:**
- Initial passwords are not forced to change at first login (no column for it in DATA_MODEL).
- Login CSRF (forcing a victim into the attacker's account) is not covered; SameSite=Lax limits it. Revisit in Phase 4 hardening.
- Per-IP limit trusts `X-Forwarded-For` (`--forwarded-allow-ips='*'`); a client can vary it to dodge the per-IP limit. The per-email limit still holds. Phase 4 hardening should trust only Render's proxy.
- PR #5 (auth) is ~620 lines including ~165 lines of tests, over the ~400 target.
- Settings for `session_*` exist but cookie `max_age` is the absolute lifetime; idle expiry is enforced server-side only.
**Questions for the human:** see "Open questions" above.
**Shared-file changes requested:** `backend/app/db/models/*` and `alembic/` (issue #4, labelled `shared`); `backend/app/main.py` (router registration in #5).

<!-- Copy this template for each phase or lane run.

### Phase N lane X: <name>  (<date time>)
**Issues / PRs:** #.. -> PR #..
**What changed:**
**Gate:**
- [x] item: evidence (command + result, or test name)
- [ ] item: why not
**How to verify (exact steps):**
1.
**Decisions made:** (also add to DECISIONS.md)
**Known gaps:**
**Questions for the human:**
**Shared-file changes requested:**
-->
