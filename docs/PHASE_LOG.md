# Phase Log

## Status board

| Phase / lane | Status (todo, running, ready-for-review, verified, cut) | Gate target | Issues | PRs | Notes |
|---|---|---|---|---|---|
| 0 | verified | Sat 17:15 | #2–#9 | #1, #55–#61 | deploy needs human (accounts); free tier for now |
| 1 | verified | Sat 19:00 | #10–#14, #64 | #65–#70 merged | live deploy checked: 63 routes, 501 when logged in, 401 when logged out |
| 2A ingest/dedupe | todo | Sat 23:00 | #15–#18, #71 | | |
| 2B donor screens | todo | Sat 23:00 | #19–#23 | | build against mocks until lane C merges #72 |
| 2C read API + donor API | ready-for-review, #73 blocked | Sat 23:00 | #24–#28, #72–#74, #87, #88 | #77–#81 merged, #83, #85 open, CLI and audit PRs | #73 waits for lane A #17 and #18; donor API moved here (D-126) |
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

### Phase 2 lane C: read API, MCP, donor API  (Sat 2026-11-14, about 18:30–21:30 MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #24 API keys → PR #77 `shared` (merged) · #25 `/api/v1` endpoints → #78 (merged) · #72 donor list, detail, timeline, unattributed → #79 (merged) · #74 contact log and next step → #80 (merged) · #26 report queries → #81 (merged) · #27 MCP server → #83 · #28 API guide → #85 · #87 `apikey` CLI → PR (base `main`) · #88 audit contact and next-step actions → PR (base `main`). **#73 donor and gift create, edit, delete: not started, blocked on lane A #17 (identity resolution) and #18 (round-robin).**
**What changed:** API keys (`cic_live_` + 32 random bytes, SHA-256 only, shown once, scope, last used, revoke) with the key-auth dependency and a 60 per minute per key limit. Six `/api/v1` read endpoints (`summary`, `retention`, `totals/by-period`, `totals/by-program`, `totals/by-board-member`, `activity/recent`) plus `health`, all aggregates in USD cents with `as_of`. The app's Reports page and `/api/v1` share one set of queries. Donor list (My/All, search, filters, pagination), detail, timeline, unattributed gifts; contact log and next step. A read-only stdio MCP server with six tools in `mcp_server/`, its own lockfile and CI job. `docs/API_GUIDE.md`. `python -m app.cli apikey {create,list,revoke}`.
**Gate** (Phase 2 gate for lane C: acceptance tests 7, 12, and 11 for retention; 1 to 4 belong to lane A):
- [x] **Test 7**, another member sees history but not email, phone or notes: `tests/integration/test_donor_read_api.py::test_other_member_sees_history_but_not_contact_details` (also checks the timeline and email search); acting on that donor returns 403: `test_contact_and_next_step.py::test_other_member_cannot_act_on_a_donor_they_do_not_own` (nothing is written).
- [x] **Test 12**, valid key returns aggregates, no key, wrong key and revoked key return 401, wrong scope 403, 61st request 429 with `Retry-After`: `test_v1_aggregates.py` (`test_no_key_wrong_key_and_revoked_key_get_401`, `test_wrong_scope_gets_403`, `test_rate_limit_is_60_per_minute_per_key_with_retry_after`). No donor PII in the schema: `test_openapi_for_v1_has_no_donor_pii_fields` walks the `/api/v1` OpenAPI document and fails on any donor name, email, phone, note or id field; `test_responses_contain_no_donor_pii` checks real responses.
- [x] **Test 11**, retention classes match the manifest, checked ahead of lane A's importer: `test_reports.py::test_retention_matches_the_fixture_manifest` loads the donors and gifts that `test_fixtures.py` resolves independently and gets 33 new, 10 reactivated, 25 increased, 18 same, 31 decreased, 40 lapsed as of 2026-11-15, with matching cents. To be repeated through the real importer once lane A lands.
- [x] Lint, types, tests: `uv run ruff check . && uv run ruff format --check . && uv run mypy app` clean (70 files); `uv run pytest` 551 passed, 2 skipped on the audit branch (559 on the CLI branch) at the last run; `cd mcp_server && uv run pytest` 20 passed, ruff and mypy clean; `npm run gen:api && npm run typecheck` clean after each route change.
- [x] MCP works end to end (run by hand, local Docker database): the server over stdio listed the six tools and returned data for all six against a local backend; a wrong key gave "The API key was rejected".
- [x] Guide examples run: every `curl` in `docs/API_GUIDE.md` was run against a local backend; example responses are the real output, including the 429 `retry-after` header and the login, create, list and revoke key flow.
- [x] Speed (NFR-7), local Docker database, 1,000 donors and 5,000 gifts, in-process test client: donor list median 146 ms (slowest run 387 ms, cold), search 69 ms, status filter 144 ms, donor detail 51 ms, timeline 46 ms, retention 164 ms, report summary 303 ms. Not measured against Neon over the network.
- [ ] #73 manual donor and gift create, edit, delete: blocked (above).
**How to verify (exact steps):**
1. Merge the open PRs with merge commits: #83, #85, the CLI PR, the audit PR, this report.
2. `docker compose up -d db`, `cd backend && uv run alembic upgrade head && uv run python -m app.cli setup`, `uv run uvicorn app.main:app`.
3. Create a key: `uv run python -m app.cli apikey create --name Dashboard --email <member email>`. Then `curl -H "Authorization: Bearer <key>" localhost:8000/api/v1/totals/by-program` returns 200; without the header 401. `apikey revoke <id>` then the same call returns 401.
4. Log in as two different members (private window). The second opens `GET /api/app/donors?scope=all` and a donor owned by the first: gift history and timeline appear, email, phone and notes are null with `contact_via` set; `POST /api/app/donors/{id}/interactions` returns 403.
5. Follow `docs/API_GUIDE.md` steps 1 and 2 on the deployed URL; for Claude Desktop follow `mcp_server/README.md`.
6. After lane A's importer lands: import all fixtures, then `GET /api/v1/retention?as_of=2026-11-15` and compare with `fixtures/manifest.json`.
**Decisions made:** D-127 (rate limit in memory), D-128 (notes are a contact detail). Also: the v1 retention response carries `retention_date` beside `as_of` because API.md used one name for two things; the stored key prefix is 13 characters (`cic_live_` + 4), not 8; `new` means first linked gift in the last 30 days; the CLI `apikey create` records the member it is for (`--email`).
**Known gaps:**
- **#73 not built** (blocked on lane A #17 and #18). Until it lands there is no way to create or edit a donor or gift by hand; `POST /donors`, `PATCH /donors/{id}`, `DELETE /donors/{id}` and `POST /donors/{id}/gifts` still answer 501.
- `thank_you_due` and `update_due` donor statuses and every `open_reminders` count are missing or 0 until the reminders service (lane A, Phase 3).
- The rate limit is per process and in memory: exact on Render's single worker, reset by a restart, not shared across workers (D-127).
- No Settings screen for API keys: issue #86 (lane B, Phase 4). Keys are made through the app API (guide step 1) or the CLI.
- API.md says Swagger shows the public tag only in production; `/api/docs` currently lists every route (Phase 4 hardening).
- Timeline and unattributed lists return at most 500 entries and are not paged.
- Speed was measured locally only (see gate), not on Neon.
- The contract test `test_api_contract.py` keeps an `IMPLEMENTED` set that every lane edits; expect small merge conflicts.
- PR sizes over about 400 lines: #78 (about 830 handwritten, 370 tests), #79 (about 640, 280 tests), #81 (about 1,100 with generated files), #83 (about 410 excluding the lockfile); the pieces in each depend on one another.
- Audit entries for the contact log and next steps were missing from #80 and are added in #88 (found while writing this report).
**Questions for the human:** Should keys expire (they never do now)? Does CIC want per-key scopes beyond `read:aggregates` (none planned)?
**Shared-file changes requested:** none open. Merged with #77: `backend/app/main.py` (router), `backend/app/errors.py` (headers), generated `frontend/src/api/openapi.json` and `types.ts`. Touched outside lane C paths with your approval: `backend/app/cli.py` (the `apikey` command) and `docs/API.md` 1.1.

### Phase 1: Schema, policy, fixtures, contracts  (Sat 2026-11-14, 16:50–17:30 MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #10 donor, gift and program tables `shared` · #64 import and relationship tables `shared` (split from #10) · #11 authorization policy `shared` · #12 assumed import formats · #13 synthetic fixtures and manifest · #14 API contract stubs and TS types `shared`. Branches are stacked `phase-1/<issue>-…`.
**What changed:** migrations 0002 and 0003 add every remaining table with the rules enforced by the database (gift has a donor exactly when linked, net = gross - fee, USD only, one live gift per `row_key`, one committed file per source, strong identities unique, message approval checks, one open draft per donor and kind, one open next step per donor). `authz/policy.py` answers every action. `docs/IMPORT_FORMATS.md` records each layout with its source and confidence. `fixtures/` holds four deterministic synthetic files plus `manifest.json`. All 63 app routes from `docs/API.md` section 3 exist with typed request and response schemas, require a session and CSRF, and answer 501 until their lane builds them; `frontend/src/api/types.ts` is generated from the OpenAPI document.
**Gate:**
- [x] Migrations apply from empty and downgrade: `test_migrations_downgrade_and_reapply` (to base and back) and `test_downgrade_to_previous_revision_and_back` pass; `alembic upgrade head` ran on a fresh database.
- [x] Policy matrix passes: `uv run pytest tests/authz` → 227 passed (180 matrix rows: 5 donor actions x 3 roles x 4 governance states plus 10 org actions x 3 x 4, then edge cases).
- [x] Generator hashes stable across two runs: `test_generator_is_deterministic_and_committed_files_are_current` regenerates twice into temp folders and compares bytes to each other and to the committed files; `test_files_match_manifest_hashes`.
- [x] Manifest test passes: `tests/integration/test_fixtures.py` → 8 passed; it recomputes counts, 19 review items and retention classes from the files with its own parsers and resolver.
- [x] Types generate without errors: `npm run gen:api` → `openapi-typescript 7.13.0 ... src/api/types.ts`; `npm run typecheck`, `lint`, `build` clean; CI step "Generated API types are current" guards drift.
- [x] Whole suite: `uv run ruff check . && uv run mypy app && uv run pytest` → clean, 466 passed, 2 skipped (public invite-accept stub has no session to test).
**How to verify (exact steps):**
1. Merge #10, #64, #11, #12, #13, #14 in that order (merge commits). Render redeploys and runs migrations 0002 and 0003 on Neon automatically.
2. After the deploy: `https://cic-compass.onrender.com/api/docs` lists the routes; a logged-in call such as `GET /api/app/donors` returns 501 `not_implemented`; a logged-out call returns 401.
3. Open `fixtures/synthetic_zeffy_like.csv`, `synthetic_benevity_like.csv` and `synthetic_cic_spreadsheet.xlsx`. Look for: the same person across files with different emails (Benevity rows with a work email), shared household emails in the spreadsheet, rows with `failed`/`pending` status, a bad date (`31/31/2025`), a `CAD` row, `Anonymous Donation` rows. `fixtures/manifest.json` lists the expected summaries.
4. Read `docs/IMPORT_FORMATS.md`, especially the "How sure are we?" table.
**Decisions made:** D-123 (policy defaults), D-124 (TypeScript 5.9 for openapi-typescript). Policy: the setup CLI is trusted; api-key and system actors never pass app policy; unknown actions are denied.
**Known gaps:**
- Stubs return 501 only, no fake data (the cut-list option); lane B builds against the generated types.
- PR sizes over ~400 lines: #10 (686, ~200 generated migration), #64 (690, ~190 generated migration), #13 (1,852, mostly the four fixture files, the generator and its test), #14 (generated `types.ts` is 5,846 lines; handwritten about 1,100). Generated and data files are marked in `.gitattributes`.
- Zeffy's **API** and Benevity's **disbursement report column names** are now documented from material a teammate supplied (`docs/IMPORT_FORMATS.md` sections 2b and 3). Still assumed: Zeffy's dashboard export layout, the exact header text, file type and date format of Benevity's export, and CIC's donor spreadsheet. Ask CIC for one real header row from each.
- `/api/v1` (public read API) is not stubbed; lane C builds it from `docs/API.md` section 1.
- Lane ownership of stub files: A has `app_donors.py`, `app_imports.py`, `app_members.py`, funder export and settings/programs; C has `app_messages.py`, templates, API keys, reports queries. Donor CRUD was not assigned in `PLAN.md`; the stubs assign it to lane A.
- `GET /api/app/donors/{id}` and friends need `Owned` resources; the policy is in place, repositories that call it arrive with lane A.
**Questions for the human:** none blocking. Optional: ask CIC for one real header row each from Zeffy, Benevity and their donor spreadsheet.
**Shared-file changes requested:** `backend/app/db/models/*`, `backend/alembic/` (#10, #64), `backend/app/authz/policy.py` and `actor.py` (#11), `backend/app/main.py`, `backend/app/schemas/*`, `frontend/src/api/types.ts` (#14).

### Phase 0: Foundation  (Sat 2026-11-14, 15:11–15:45 MST)
**Issues / PRs (merge in this order):** #2 → PR #1 (merged) · #3 skeleton · #4 tables (`shared`) · #5 auth · #6 CLI · #7 app shell · #8 CI + Docker · #9 deploy + costs. Branches are stacked (`phase-0/<issue>-…`), each on the previous one.
**What changed:** FastAPI backend (settings, Phoenix clock, typed errors, healthz, Alembic), people/access tables with DB-enforced governance rules, Argon2id login with hashed sessions, double-submit CSRF and audit-based rate limit, operator CLI, React shell with login and 7-section nav, CI (ruff, mypy, pytest on Postgres, tsc, eslint, prettier, build, docker build, gitleaks), single-image Dockerfile, `render.yaml`, `docs/COSTS.md`. Issue #4 was split out of the auth issue to keep PR size down.
**Gate:**
- [x] CI green: PR #61 (full stack) passed backend, frontend, container, gitleaks and lint on GitHub Actions. Every step passes locally: `uv run ruff check . && uv run mypy app` → clean; `uv run pytest` → 28 passed; `npm run typecheck && npm run lint && npm run build` → clean.
- [x] `docker compose up` + `alembic upgrade head` + `cli setup` from empty: dropped and recreated `cic`, `alembic upgrade head` → "Running upgrade -> 0001", `python -m app.cli setup --file …` → two members created, passwords printed once.
- [x] Logged-out calls get 401: `test_logged_out_calls_get_401`; curl to `/api/app/auth/me` on the Docker image → 401.
- [x] Two members log in separately: `test_two_members_log_in_separately`.
- [ ] Deployed URL serves login and `/healthz`: needs the human to create Neon + Render (docs/DEPLOY.md). Locally the production image serves `/login` 200 and `/healthz` `{"status":"ok"}`.
- [x] No secrets in git: `gitleaks git --redact` (v8.24.0) → "21 commits scanned … no leaks found".
- [x] `COSTS.md` within budget with sources: $0/month now (Render free + Neon free + Resend free); ≈ $7/month production on Render Starter (dollar price unverified, marked).
**How to verify (exact steps):**
1. Merge PRs in the order above (each PR's base retargets to `main` as the one below merges).
2. Locally: `docker compose up -d db`, `cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.cli setup`, `uv run pytest`.
3. `cd frontend && npm ci && npm run dev`, open http://localhost:5173 in two browsers (one private) and log in as two different members; each sees their own name. Log out works; 6 wrong passwords → "Too many attempts".
4. Follow docs/DEPLOY.md, then log in on the Render URL in a private window as two members; open `/healthz`.
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
