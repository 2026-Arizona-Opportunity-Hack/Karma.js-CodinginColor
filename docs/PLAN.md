# CIC Compass: Phase Plan (v3, FastAPI, parallel lanes)

Times are Arizona (MST). Hard dates from the repo README: **feedback hour Sun 11:00**, **start recording Sun 12:00**, judges arrive 12:30, **hacking ends Sun 14:00**.

## 1. How we work

### 1.1 The loop
```
Human: "Run Phase N" (or "Run Phase N lane A")
  Agent: opens/uses the GitHub Issues for that phase, builds each issue on its own branch,
         keeps each PR under ~400 changed lines, runs checks, opens PRs with the repo template,
         writes the phase report in docs/PHASE_LOG.md, STOPS.
Human: verifies (report steps + "Human verification" below), merges PRs in the listed order.
  pass -> "Run Phase N+1"
  fail -> "Fix Phase N: <what failed>"
Optional: a separate session runs "Review Phase N" (read-only, tries to break it).
```
Agents never start the next phase on their own.

### 1.2 Repo rules that shape the plan (from the organizers' `AGENTS.md`)
- One repository: all code here.
- **One change per PR, under 400 changed lines**, imperative title under 72 chars, description under 500 words in template order (what, why, how to test, screenshots). Open with `gh pr create`. Never force-push a shared branch.
- **One GitHub Issue per task or decision**, closed by the PR that lands it (`Closes #N`). Phase 0 creates the issues listed below.
- Secrets only in `.env`; the repo hook blocks commits containing keys or `.env`.
- README kept current (what, how to run, live link, demo link).
- After 12:00 Sunday: no new features.

Lockfiles and Alembic migrations inflate line counts. Put a dependency or lockfile change in its own small PR when possible; the PR lint only comments, it never blocks.

### 1.3 Parallel lanes
After Phase 1 freezes the schema and contracts, three agents work at once in separate git worktrees:

| Lane | Owns (only these paths) | Hat |
|---|---|---|
| **A: Core backend** | `backend/app/services/{ingest,dedupe,ownership,reminders}/`, their `repos/`, `routes/app_imports.py` and `routes/app_ownership.py`, their tests | backend engineer |
| **B: Web app** | `frontend/` | frontend engineer |
| **C: API, messaging, ops** | `backend/app/routes/v1/`, `backend/app/services/{apikeys,messaging,reports,donors}/`, their repos and routes (including `routes/app_donors.py`, moved here in Phase 2, D-126), `mcp_server/`, `docs/API_GUIDE.md`, CI and deploy files, their tests | backend + devops |

Phase 4 moves `services/reports/` to lane A (funder export, lapsed radar) because lane C is hardening; lane C's hardening changes to `main.py` and middleware go through `shared` PRs.

**Shared files** (`backend/app/db/models/*`, `alembic/`, `backend/app/schemas/*`, `backend/app/authz/policy.py`, `backend/app/main.py`, `frontend/src/api/types.ts`) change only in a dedicated small PR labelled `shared`, merged before dependent lane PRs. If a lane needs a shared change, it opens that PR first and says so in the phase report.

```bash
# one worktree per lane
git worktree add ../cic-lane-a -b lane-a/base main
git worktree add ../cic-lane-b -b lane-b/base main
git worktree add ../cic-lane-c -b lane-c/base main
```
Branch per issue: `lane-a/12-row-key-dedupe`. Rebase on `main` before opening a PR.

## 2. Schedule

| Phase | What | Lanes | Gate (target) |
|---|---|---|---|
| 0 | Foundation: layout, auth, setup CLI, shell, CI, deploy, issues | single agent | Sat 17:15 |
| 1 | Schema, policy, fixtures, contracts | single agent | Sat 19:00 |
| 2 | Ingest + dedupe + review · Donor screens · Read API + MCP | A, B, C | Sat 23:00 |
| 3 | Ownership + governance + reminders · Dashboard + reassignment UI · Messaging backend | A, B, C | Sun 01:30 |
| rest | Sleep | | 01:30 to 06:00 |
| 4 | Messaging UI · Retention + funder export + lapsed radar · Hardening | A, B, C | Sun 09:00 |
| 4.5 | CIC Nov 15 requirements: Zeffy contacts, board member column, custom fields, scheduled emails, branding | A, B, C | Sun 10:15 |
| 5 | Accessibility, acceptance on production, trust report | single agent + human | **Sun 10:30 freeze** |
| 5.5 | Custom roles and permissions (ROLE) | A, B, C | Sun 11:45, hard stop |
| 6 | Docs, draft video (10:45), feedback hour (11:00), record (12:00), submit | human + writer agent | **Submit by 13:30** |

If a gate is more than 45 minutes late, apply that phase's cut list. **Never cut:** idempotent import with summary, round-robin, Needs reassignment, approval-gated messaging, reminders To-do, read API (minimal), authorization tests, deployment, README, the video, the 30-minute submission buffer.

---

## 3. Phases

### Phase 0: Foundation (single agent)

**Issues / PRs (in merge order)**
1. `Add project docs and agent rules`: copy this kit's `docs/`, `.claude/skills/`, append the project section to `AGENTS.md`; create GitHub Issues for Phases 0 to 6 from this file (`gh issue create`), labels `phase-N`, `lane-X`, `shared`.
2. `Add FastAPI backend skeleton`: `backend/` with pyproject (ruff, pytest), settings from env, `/healthz`, Alembic init, `docker-compose.yml` for local Postgres.
3. `Add users, sessions and governance tables with auth`: tables from DATA_MODEL 2.1, Argon2id, login/logout/me, CSRF, login rate limit, audit writer.
4. `Add setup CLI for board members and super admin`: `python -m app.cli setup | superadmin {create,flatten,transfer,deactivate} | seed-demo | reset-demo`.
5. `Add React app shell with login`: Vite + TS + Tailwind, router, TanStack Query, login page, nav (Dashboard, Donors, Import, Review, Messages, Reports, Settings), API client with CSRF header.
6. `Add CI and container build`: GitHub Actions (ruff, pytest with Postgres service, frontend typecheck + build, gitleaks), Dockerfile (builds SPA, FastAPI serves it).
7. `Deploy to Render with Neon and record costs`: `render.yaml`, env vars documented in `.env.example`, `docs/COSTS.md` with current prices from the vendors' pages and plan terms (Render Starter, Neon free, mail provider), total within $20/month.

**Agent gate:** CI green; `docker compose up` + `alembic upgrade head` + `cli setup` works from empty; logged-out calls get 401; two members log in separately; deployed URL serves login and `/healthz`; no secrets in git; `COSTS.md` within budget with sources.
**Human verification:** log in on the deployed URL in a private window as two different members; read `COSTS.md` against vendor pages.
**Cut list:** skip gitleaks (repo hook covers commits); deploy at end of Phase 1 instead.

### Phase 1: Schema, policy, fixtures, contracts (single agent)

1. `shared` `Add donor, gift and import tables`: all remaining tables, checks, partial unique indexes (DATA_MODEL 2.2 to 2.5); `docs/DATA_MODEL.md` updated if anything changed.
2. `shared` `Add authorization policy with matrix tests`: `authz/policy.py` per DATA_MODEL 3.6; table-driven tests for every action x role x ownership x governance state.
3. `Document assumed import formats`: research Zeffy's public API docs (payment, contact, campaign objects) and Benevity's donation report glossary; write `docs/IMPORT_FORMATS.md` with columns per source, the generic template, sources and the word **assumed**. Do not invent columns a source does not document; where unknown, use the generic template.
4. `Add synthetic fixture generator and manifest`: DATA_MODEL section 4; deterministic; an independent test recomputes the manifest.
5. `shared` `Add app API contract stubs and TS types`: Pydantic request/response schemas for every route in API.md section 3, routes returning `501` or fixture-backed fakes; `openapi-typescript` generates `frontend/src/api/types.ts`. This is what lets lanes A, B, C run in parallel.

**Agent gate:** migrations apply from empty and downgrade; policy matrix passes; generator hashes stable across two runs; manifest test passes; types generate without errors.
**Human verification:** open the fixtures and spot duplicates across files, anonymous rows, a bad date, a non-USD row; read IMPORT_FORMATS.md sources.
**Cut list:** stubs return `501` only (no fake data); skip downgrade tests.

### Phase 2: Parallel build 1

**Lane A: ingest, dedupe, review**
1. `Add source adapters and normalizers` (spreadsheet, Zeffy, Benevity, generic; CSV and XLSX; size and type checks).
2. `Add import preview with row keys and summary` (row_key 3.1, classification, invalid reasons, program mapping, cutoff).
3. `Add donor identity resolution and review queue` (DED-3 to DED-6, DED-8).
4. `Add import commit with round-robin assignment` (single transaction, advisory lock, owner_history, file hash block, batch history, reverse).
5. `Add attribute action for anonymous gifts` (#71; after 3, small).

**Lane B: donor screens** (build against stubs, switch to live endpoints as A merges)
1. `Add donor list with My/All toggle and cards` (DON-1, DON-5, search, filters).
2. `Add donor detail page with timeline` (DON-6, contact fields hidden per DON-3).
3. `Add donor and gift create/edit forms with duplicate warning` (DON-7, DON-8, DED-6 `409` flow).
4. `Add import upload, summary and review screens` (ING-4/5, DED-4).
5. `Add log-contact sheet and next step` (DON-9, DON-10; 3 taps at 390 px).

**Lane C: read API and MCP**
1. `Add API keys with hashing, scopes and revoke`.
2. `Add aggregated read endpoints` (`/api/v1/*`, rate limit, PII-free schema test).
3. `Add report queries for summary and retention` (shared by `/api/v1` and the app's Reports page).
4. `Add read-only MCP server` (`mcp_server/`, README for Claude Desktop config).
5. `Add API guide with curl examples` (`docs/API_GUIDE.md`).
6. `Add donor list, detail, timeline and unattributed endpoints` (#72; acceptance test 7; **do this right after item 1, lane B waits on it**).
7. `Add contact log and next step endpoints` (#74).
8. `Add donor and gift create, edit and delete endpoints` (#73; **after lane A items 3 and 4 merge**, it needs candidate matching and round-robin).

Lane C's order: 1, 2, 6, 7, 3, 8, 4, 5. The donor API moved here from lane A because lane A carries the import pipeline (D-126).

**Gate:** acceptance tests 1, 2, 3, 4 (owner on import), 7, 12 as integration or e2e tests.
**Human verification:** import all fixtures on the deployed app; compare summaries to `manifest.json`; re-upload; resolve one review item; call the API with a new key, then revoke it.
**Cut list:** batch reverse UI (keep endpoint); filters beyond owner and status; MCP to Phase 4; attribute action (#71); manual donor create and edit (#73, keep the read endpoints).

### Phase 3: Parallel build 2

**Lane A: ownership, governance, reminders**
1. `Add manual and bulk reassignment with owner history` (OWN-3, OWN-4, scope checks).
2. `Add member invites and deactivation with Needs reassignment` (AUTH-4, AUTH-7, OWN-5).
3. `Add governance scope and flatten endpoints` (GOV-4, GOV-5, audit).
4. `Add derived reminders service` (REM-1 to REM-4, DATA_MODEL 3.4, injected clock tests). Lane C (#38) already writes the send record: an `interactions` row with `kind`, `donor_id`, `message_id` and `gift_id` for every sent or manually-sent message (DATA_MODEL 3.4). The reminders service must read these existing rows to clear thank-you and quarterly reminders. Do not add a new table or column for this. Match gifts (`is_matching_gift`) never create thank-you reminders (D-127).

**Lane B: dashboard and people**
1. `Add dashboard To-do and Needs reassignment list` (REM-5).
2. `Add reassign dialog and owner history` (respecting scope).
3. `Add members and governance settings pages` (invite, deactivate, scope, flatten button for super admin).

**Lane C: messaging backend**
1. `Add message templates and drafts` (MSG-1, MSG-2, idempotency).
2. `Add approval state machine with database checks` (MSG-3, MSG-4).
3. `Add email dry-run sender, SMS mark-sent and send history` (MSG-5 to MSG-7, clears reminders).
4. `Add reminder digest send` (REM-6, dry-run, per-member content; depends on lane A issue 4, merge after it).

**Gate:** acceptance tests 5, 6, 8, 10; API tests for 9.
**Human verification:** deactivate a member and watch Needs reassignment; reassign; switch scope with the super admin; flatten; draft and approve a message via API docs page.
**Cut list:** bulk move UI; digest per-member preview (send only).

### Phase 4: Parallel build 3

**Lane A: reports and P1**
1. `Add funder export with program outcomes` (RPT-3, HTML + CSV with formula neutralizing).
2. `Add lapsed-donor radar with drafted nudges` (our P1 pick).

**Lane B: messaging and reports UI**
1. `Add message drafts, approve and send screens` (dry-run badge, sms link, mark sent).
2. `Add retention view and dashboard summary` (RPT-1, RPT-2).
3. `Add settings for templates, programs and program map`.

**Lane C: hardening**
1. `Add security headers, CSP and rate limits` (NFR-1).
2. `Add audit coverage test and export audit` (every listed action writes audit; DON-12).
3. `Add demo seed and reset for DEMO_MODE`.

**Gate:** acceptance tests 9, 11; full suite green on `main`.
**Cut list:** template editing (read-only templates); program map UI (seeded map only); lapsed radar.

### Phase 4.5: CIC requirements update (Nov 15)

New requirements from CIC on Sunday morning (SRS ING-12 to ING-14, DON-13, REM-9, MSG-9, CUS-1 to CUS-4, GOV-2, GOV-3, NFR-10; D-136 to D-144). Lanes are flexible for this phase: any agent may take any item. Run lanes after their Phase 4 lane is merged. The CUS migration lands first as a `shared` PR.

**Shared (first):** `Add field definitions, custom values, nominations and job runs schema` (migration: `field_definitions` seeded with built-ins, `donors.custom`, `gifts.custom`, `super_admin_nominations`, `job_runs`, new `app_settings` keys; models; schemas; regenerate `types.ts`).

**Lane A: imports**
1. Arbitrary file layouts (ING-12): built separately by a teammate (AI-assisted mapping); not part of this phase's agents.
2. `Read the board member column on every import` (ING-13; owner for new donors; approved owner change for existing; preview lists unmatched).
3. `Import columns that match custom fields` (ING-14).

**Lane B: screens and brand**
1. `Apply CIC brand theme` (NFR-10, `docs/BRAND.md`; Tailwind tokens; logo slot; recheck contrast).
2. `Expand donor rows to show gift history` (DON-13).
3. `Add field settings and dynamic field rendering` (CUS-1 to CUS-4; donors and gifts; list columns).
5. `Add super admin nomination, confirmation and removal screens` (GOV-2, GOV-3).
4. `Show Zeffy contacts preview, board member and ignored columns` (ING-12 to ING-14 in the import screen).

**Lane C: custom field API and scheduled jobs**
1. `Add field definition and value endpoints` (CUS-1 to CUS-4, validation by type, audit, policy).
4. `Add super admin nomination and removal` (GOV-2, GOV-3, D-144; two different members; only the super admin removes; flat afterwards; audit; CLI unchanged).
2. `Add run-job CLI, job_runs and quarterly board email` (REM-9, D-138; dry-run mail by default; `render.yaml` cron, disabled by default).
3. `Add auto thank-you setting and job` (MSG-9, D-139; off by default; dashboard banner data).

**Gate:** a board member column assigns the owner; a donor and a gift field can be added, filled, renamed and deactivated without losing values; a super admin is created by nomination plus confirmation and removed by themselves, leaving the org flat; `run-job quarterly_board_email` records one dry-run email per member with only their donors; full suite green.
**Cut list (in order):** MSG-9 auto thank-you (keep the setting off, document it); multi-choice fields; gift fields (keep donors); ING-14 field import; nomination expiry job (manual cancel only). **Never cut** ING-13, CUS add/rename/deactivate on donors, super admin removal, the brand theme.

### Phase 5: Accessibility and acceptance (freeze 10:30)
1. `Fix accessibility to Lighthouse 95+` (Lighthouse CI on main pages; keyboard path; 390 px).
2. `Add acceptance e2e suite against deployed URL` (tests 1 to 13; Playwright + axe).
3. `Add trust report` (`docs/TRUST_REPORT.md` generated from the real run with timestamp: tests passed, Lighthouse scores, policy matrix size, audit coverage).

**Gate:** all 13 acceptance tests pass on production (output pasted); Lighthouse scores listed.

### Phase 5.5: Custom roles and permissions (after the Phase 5 gate)

SRS ROLE-1 to ROLE-6, D-143. Changes authorization after acceptance, so it ships only if the full policy matrix and acceptance tests 5, 6, 7 and 12 pass again on production. **Hard stop 11:45**: anything not merged by then moves to the roadmap; nothing merges after 12:00 recording starts.

**Shared (first, lane C opens it):** `Add roles table and role-based checks to policy` (migration with seeded Board member and Viewer, `users.role_id`, `Action.ROLES_MANAGE`; `can()` checks the actor's role for org-wide actions and the two donor-wide grants; the policy matrix proves Board member equals today's behaviour).

**Lane C:** `Add role endpoints with lockout guard and audit` (ROLE-3, ROLE-5, ROLE-6).
**Lane B:** `Add roles settings screen and member role picker` (ROLE-1, ROLE-3; plain permission labels; brand theme).
**Lane A:** `Extend policy matrix and acceptance tests for roles` (Viewer cannot import or act; a custom role with "Act on any donor" can; governance actions never grantable; lockout refused).

**Gate:** policy matrix green including the new role cases; acceptance 5, 6, 7, 12 pass on production after deploy; a member's role changed in the UI takes effect on their next request.
**Cut list (in order):** role delete; Viewer role; lane B screen (roles then managed by CLI only, documented). If the shared PR is not green by 11:15, stop the phase and keep it as roadmap.

### Phase 6: Docs, video, submission (human-led; writer agent edits docs only)
- README: what we built, team, tech stack, run locally, live link, demo link, screenshots.
- `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md` (deploy, rotate keys, super admin CLI, restore), `docs/HANDOFF_TO_CIC.md` (accounts to transfer: GitHub, Render, Neon, mail provider), `docs/ROADMAP.md` (improve-later list from SRS 3.2 as GitHub Issues).
- `docs/DEMO_SCRIPT.md`, 4 minutes max: (1) messy files to one ledger with the import summary and re-upload, (2) board member's To-do on a phone, log a contact, (3) draft, approve, send a thank-you, (4) Needs reassignment and owner history, (5) retention and funder export, a custom field added live, the CIC-branded UI, (6) API call and MCP in Claude, (7) security: board member blocked from another's contact details, audit log.
- 10:45 draft recording → 11:00 feedback hour → 12:00 record final → upload → Team Dashboard story + video link → **Submit by 13:30**. Close remaining issues or move them to the roadmap label.
