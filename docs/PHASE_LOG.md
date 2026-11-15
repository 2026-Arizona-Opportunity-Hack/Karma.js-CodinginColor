# Phase Log

## Status board

| Phase / lane | Status (todo, running, ready-for-review, verified, cut) | Gate target | Issues | PRs | Notes |
|---|---|---|---|---|---|
| 0 | verified | Sat 17:15 | #2–#9 | #1, #55–#61 | deploy needs human (accounts); free tier for now |
| 1 | verified | Sat 19:00 | #10–#14, #64 | #65–#70 merged | live deploy checked: 63 routes, 501 when logged in, 401 when logged out |
| 2A ingest/dedupe | ready-for-review | Sat 23:00 | #15–#18, #71, #84, #102 | #82, #89, #98, #99, #101, #103 | local acceptance 1–4 pass; documentation publication and human merge/verification pending |
| 2B donor screens | todo | Sat 23:00 | #19–#23 | | build against mocks until lane C merges #72 |
| 2C read API + donor API | ready-for-review | Sat 23:00 | #24–#28, #72–#74, #87, #88 | #77–#81 merged, #83, #85, #90, #91 open | #73 built in two PRs after lane A's #17 and #18 merged; donor API moved here (D-126) |
| 3A ownership/reminders | ready-for-review | Sun 01:30 | #29–#32 | #118, #119, #121, #122 | merge in that order |
| 3B dashboard/people | todo | Sun 01:30 | | | |
| 3C messaging backend | ready-for-review | Sun 01:30 | #36–#39, #100, #113, #126 | #108–#111, #114 merged; PR #128, PR #129 open | no messaging UI until lane B Phase 4 |
| 4A reports/P1 | ready-for-review | Sun 09:00 | #40, #135, #41 | #134, #136, #137, #138 | merge in that order; #136 and #137 are stacked on #134 |
| 4B messaging/reports UI | todo | Sun 09:00 | | | |
| 4C hardening | ready-for-review | Sun 09:00 | #45, #46, #47 | #131, #133, #141 | merge in that order; #131 is `shared` (main.py) |
| 4.5 CIC Nov 15 update | todo | Sun 10:15 | | | new SRS ING-12 to ING-14, DON-13, REM-9, MSG-9, CUS, NFR-10; shared migration PR first |
| 5 a11y/acceptance | todo | Sun 10:30 | | | |
| 5.5 custom roles | todo | Sun 11:45 hard stop | | | SRS ROLE-1 to ROLE-6, D-143; ships only if policy matrix and acceptance 5, 6, 7, 12 pass again |
| 6 docs/video/submit | todo | Sun 13:30 | | | |

## Phase 3 targeted work: confirmed spreadsheet updates (#105)

**Scope:** one shared PR for the requested lane A backend, typed API contract and
lane B import dialog. This does not start the remaining Phase 3 lanes. Separate
deploy-note issue #106 is published as PR #107, branch
`phase-3/106-single-process-note`, commit `badb16c`.

**What changed:** existing DED-3 spreadsheet matches propose name, organization,
email, phone and notes changes. The uploader selects fields in a modal with all
checkboxes unchecked. Only approved fields change, with one audit per donor in
the import transaction. DON-3 controls old-value visibility; ownership never
changes. Missing columns preserve data; approved empty cells clear fields.
Update rows participate in physical-row reconciliation, with unique-donor
`updated_count`. Stale selected fields fail atomically; rejected contacts are
not learned as donor identities. No model or migration changes.

**Requirements:** ING-4, ING-5, ING-8, DED-3, DON-3; decision D-130.

**Backend verification:** before syncing main, `pytest -p no:cacheprovider`
reported `636 passed, 2 skipped`; after the final matching fix, the focused
importer command below reported `47 passed` (including acceptance tests 1-4):

```text
pytest -p no:cacheprovider tests/unit/test_spreadsheet_updates.py tests/unit/test_import_preview.py tests/integration/test_spreadsheet_updates.py tests/integration/test_import_preview.py tests/integration/test_import_commit.py
```

After syncing `origin/main` at `ec6ef93`, `ruff check app tests` passes and
`mypy app` reports `Success: no issues found in 96 source files`.
The final merged-branch full run includes all importer tests and reports:

```text
pytest -p no:cacheprovider
1 failed, 695 passed, 2 skipped, 1 warning in 600.80s (0:10:00)
FAILED tests/integration/test_contact_and_next_step.py::test_completing_a_step_logs_an_interaction_and_clears_the_card
```

The two skips remain the intentional public invite-accept session/CSRF cases;
no importer or donor-update test is skipped. The warning is the existing
Starlette/httpx TestClient deprecation. See the clock/timeline gap below.

**Verification:** frontend `npm run typecheck`, `npm run lint`,
`npm run test:updates` (3 passed), and `npm run build` pass. With
`npm run dev -- --host 127.0.0.1 --port 5173` running, execute
`node tests/import-updates.browser.mjs` (Node 22+, local Chromium; optionally set
`CHROME_PATH`). The browser test mocks all API calls with synthetic data and
checks unchecked defaults, modal focus, Space selection, 390px width, empty
approvals and an email-only commit payload. Screenshot:
[donor update review](screenshots/105-donor-updates.png).

**Known limits:** preview storage remains process-local and expires after 20
minutes. Import history/reversal and identity review UI remain separate lane B
work. Existing batch reversal semantics remove gifts/new donors; reversal does
not restore approved edits to existing donor fields. Parent importer PRs must
merge before this feature PR. Tests use only local PostgreSQL, never Neon.

The merged-branch full suite exposes an unrelated existing failure:
`test_completing_a_step_logs_an_interaction_and_clears_the_card` in
`tests/integration/test_contact_and_next_step.py:207`. Its fixed clock dates the
completion note at Phoenix midnight, while the next-step creation timestamp
uses the database's real clock. Once the real date reaches November 15, the
next-step item sorts ahead of the completion note. A single-test run on a
separate local test database reproduces `1 failed` (`next_step` versus expected
`note`). The test, relationship repository, donor repository and contacts
service are unchanged from `origin/main` at `ec6ef93`. This clock/timeline fix
is outside the requested spreadsheet feature; do not treat the full gate as
green until it is addressed separately.

## Open questions for the human / CIC
- Should initial passwords from `cli setup` force a change at first login? Not in the data model today (see Phase 0 known gaps).

## Ideas (out of scope, for later)
- `cli reset-password --email X` for when a member loses the initial password.
- Change-password page in Settings.

## Reports

### Phase 4 lane C: hardening  (Sun 2026-11-15, morning MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #45 security headers, CSP, rate limits `shared` → PR #131 · #46 audit coverage test → PR #133 · #47 demo seed and reset → PR #141. No migrations. No stacking; each is based on `main`.
**What changed:** Every response now carries CSP (self only, no inline scripts, `frame-ancestors 'none'`), HSTS, nosniff, X-Frame-Options, Referrer and Permissions policies; only `/api/docs` may load the Swagger viewer from jsDelivr. In-memory per-IP limits: 20 login attempts and 300 requests per minute on `/api/app/*`, 429 with `Retry-After` in the normal error shape (off when `APP_ENV=test`). A test now fails if an audited action is added, dropped or untested, if an SRS NFR-2 category loses its actions, or if the app can update/delete audit rows; eight untested actions got a one-line assertion in the test that already drives them. `seed-demo` imports the four synthetic files through the real importer (refuses on a database with donors); `reset-demo` now restores programs, settings and governance after its wipe (it did not before, so a reset database could not import: "The General program is missing"). The Dockerfile copies `fixtures/`.
**Gate** (acceptance tests 9 and 11, full suite):
- [x] **Test 9** (draft, approve, send, no network in dry run): `test_message_send.py::test_dry_run_thank_you_draft_approve_send_and_it_makes_no_network_call` PASSED.
- [x] **Test 11** (retention classes match the manifest): `test_reports.py::test_retention_matches_the_fixture_manifest` and `test_import_commit.py::test_finished_importer_matches_manifest_and_acceptance_1_to_4` PASSED (`uv run pytest ... -k "dry_run_thank_you or manifest"` → 3 passed).
- [x] Full suite on the #47 branch (contains #45/#46 changes only via main merges, so rerun once all three are merged): `uv run pytest` → 627 passed; `ruff format --check .` → 158 files already formatted; `ruff check .` → All checks passed; `mypy app` → no issues found in 111 source files.
- [x] New tests: `test_security_headers.py` (4), `test_audit_coverage.py` (4 + 2 pending-skips), `test_demo_seed.py` (5).
- [ ] Not run: GitHub CI on the three PRs, anything against Render or Neon, the frontend (no frontend change), the SPA under the new CSP in a real browser.
**How to verify (exact steps):**
1. Merge #131, #133, #141 with merge commits. Render redeploys; no migrations.
2. Headers: `curl -sI https://cic-compass.onrender.com/healthz` shows `content-security-policy`, `strict-transport-security`, `x-content-type-options: nosniff`, `x-frame-options: DENY`. Open the site and `/api/docs` in a browser with the console open: no CSP violations (report any `Refused to ...` line).
3. Rate limit: 21 wrong-password `POST /api/app/auth/login` calls within a minute from one address → the 21st returns 429 with `Retry-After`. Wait a minute and a correct login works.
4. Demo (only on a demo database with `DEMO_MODE=true`, never the real one): `python -m app.cli reset-demo` prints three passwords once and four "imported ..." lines; log in as `diana@demo.cic.test`; the donor list is full and Needs review shows open items. Without `DEMO_MODE`, both commands refuse.
**Decisions made:** The rate limits are in memory, per IP, exact for Render's single worker, reset on restart. The CSP allows inline style attributes only (`style-src-attr`), not inline style or script elements. Funder export audit (`report.funder_export`) and merge audit (`donor.merge`) are listed as pending in `test_audit_coverage.py`; when lane A / the merge endpoint land them, those two tests fail until the actions move into the required list.
**Known gaps:**
- The per-IP limit uses `request.client`, and uvicorn runs with `--forwarded-allow-ips='*'`, so a client can vary `X-Forwarded-For` to dodge it (also noted in the Phase 0 gaps). Fix is to trust only Render's proxy range, a Dockerfile `CMD` change that needs Render's addresses; not done.
- The CSP was tested for headers only, not rendered in a browser; if the built SPA injects an inline `<style>` or script, the page will break and the fix is a one-line CSP change in `app/middleware.py`.
- Rate limits and counters live in memory: a restart clears them and several workers would each count separately.
- The audit coverage test checks that each action is named in some test, not that the test asserts it.
- `reset-demo` has no confirmation prompt (only `DEMO_MODE`). Merge audit (DED-7) and export audit are not covered until those features land.
**Questions for the human:** none blocking.
**Shared-file changes requested:** `backend/app/main.py` (one line adding the middleware) in PR #131, labelled `shared`, merge first. `Dockerfile` also changed in PR #141 (lane C deploy file).

### Phase 4 lane A: funder export and lapsed radar  (Sun 2026-11-15, MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #40 outcomes hand entry → PR #134 · #40 funder export → PR #136 (stacked on #134: it reads outcomes through its repo) · #135 outcomes CSV upload → PR #137 (stacked on #134: extends its files) · #41 lapsed radar → PR #138 (independent). No migrations. No shared-file changes (response models live in `services/reports/lapsed.py`). One lane C file change you approved, inside PR #138: `messaging/defaults.py` and `messaging/service.py` (the `lapsed_nudge` kind and default text).
**What changed:** `GET/POST /program-outcomes` (members read; writing follows `programs.manage`; audited). `GET /reports/funder/{donor_id}?format=html|csv&from=&to=` (default last 12 months): the donor's own gifts by program and year, the outcomes of those programs, and a note plus count of employer matches left out (D-127). Any member may export gift history; email, phone and notes appear only for the owner or an active super admin (D-104, D-129). Every export writes `report.funder_export` (dates and a contact-included flag, no names). CSV cells starting `= + - @` get a leading apostrophe; HTML escapes every value. `POST /program-outcomes/upload`: CSV only, 1 MB, all or nothing, bad rows named. `GET /reports/lapsed` lists lapsed donors per owner (lane C's `retention.build`, unchanged; no do-not-contact; no employer matches). `POST /reports/lapsed/draft` drafts a `lapsed_nudge` for each of my lapsed donors through lane C's `create_draft` (idempotent, owner-only); nothing is approved or sent.
**Gate** (acceptance test 11 and the export checks):
- [x] **Test 11, retention classes through the real importer:** `test_import_commit.py::test_finished_importer_matches_manifest_and_acceptance_1_to_4` (existing, imports the four fixture files and compares `retention.build` to the manifest) and `test_lapsed_radar.py::test_real_importer_lapsed_radar_matches_the_manifest_acceptance_11` (same import; the retention report equals `manifest.json` and the radar lists the manifest's 40 lapsed donors). `test_reports.py::test_retention_matches_the_fixture_manifest` also PASSED.
- [x] **Export audit:** `test_funder_export.py::test_every_export_writes_an_audit_entry_without_contact_details` PASSED.
- [x] **Formula neutralizing and escaping:** `test_csv_cells_that_start_like_formulas_are_neutralized` and `test_html_escapes_every_value` PASSED. Also PASSED: `test_contact_and_notes_only_for_the_owner`, `test_csv_has_own_giving_outcomes_and_the_match_note_without_the_match`, `test_missing_donor_and_bad_dates_are_refused`.
- [x] Lapsed rules PASSED: `test_lists_lapsed_donors_per_owner_without_opt_outs_or_employer_matches`, `test_drafting_nudges_only_for_my_reachable_donors_and_is_idempotent` (MSG-2), `test_a_member_cannot_draft_for_someone_elses_lapsed_donor_and_dnc_is_refused` (MSG-8, 403), `test_the_list_shows_the_open_draft_and_no_message_is_sent`.
- [x] Full suite on each PR branch, run with `TEST_DATABASE_URL=postgresql+psycopg://cic:cic@localhost:5432/cic_test_a uv run pytest`: #134 621 passed · #136 625 passed · #137 625 passed · #138 628 passed. On each branch `uv run ruff format --check .`, `uv run ruff check .` and `uv run mypy app` were clean; `npm run gen:api && npm run typecheck` clean after each route change.
- [ ] Not run: GitHub CI, frontend lint and build, anything against Render or Neon, and a combined run of all four branches together (each was tested on its own; expect small conflicts in `openapi.json`, `types.ts` and `test_api_contract.py`).
**How to verify (exact steps):**
1. Merge #134, #136, #137, #138 in that order. After each, if GitHub shows conflicts, merge `main` into the branch, take both sides in `test_api_contract.py`, then `cd backend && uv run python -m app.export_openapi ../frontend/src/api/openapi.json && cd ../frontend && npm run gen:api`.
2. Post-deployment test on `https://cic-compass.onrender.com/api/docs` (logged in; Render is in `live` mode, but nothing here sends mail): `POST /api/app/program-outcomes` with a program id, dates, label, value, unit → 201; `GET` lists it. Upload a CSV with the header `program,period_start,period_end,metric_label,value,unit,source_note` to `POST /program-outcomes/upload` → 201; put a typo in one program name → 400 naming the row, nothing saved. `GET /api/app/reports/funder/{donor_id}?format=html` for a donor with gifts: gifts by program, outcomes and the employer-match note; `?format=csv` downloads; for a donor you do not own there is no email, phone or notes. Check the audit log for `report.funder_export`. `GET /api/app/reports/lapsed` shows lapsed donors per owner; `POST /reports/lapsed/draft` → drafts for your own donors; call it again → `skipped_existing`. `GET /api/app/messages?status=draft` lists them; they stay drafts until you approve.
**Decisions made:** Who may export: any member (gift history is open, D-104); contact details and notes appear only when `donor.view_contact` allows it, so the same export differs by viewer. Period is `from`/`to`, default the last 12 months. "By program and period" is one row per program and calendar year. Outcomes shown are those whose dates overlap the period for the programs the donor gave to. Writing outcomes uses `programs.manage` (a plain member is refused while a super admin is active). Upload is 1 MB and `.csv` only (the importer's bounded CSV reader is reused for parsing). The radar uses the rolling basis only. Drafts: email if the donor has one, else text; donors with neither are skipped; unassigned donors are listed but cannot be drafted (`can_draft: false`). `GET /templates` now lists six templates (lapsed nudge email and text added).
**Known gaps:**
- No screens: all of this is API only until lane B builds the reports and messaging UI. The funder export is a printable HTML page, not a PDF.
- The lapsed nudge text is generic (no gift amount or program, on purpose, so an employer match can never supply an amount); the owner edits it before approving.
- The radar only drafts for the signed-in owner; the super admin cannot bulk-draft for everyone.
- "Per funder" means a donor row, for example one of kind organization; there is no separate funder record, and outcomes are tied to programs and dates, not to a specific funder.
- A CSV outcomes row that exactly duplicates an earlier one is saved again (no dedupe).
- PRs #136 and #137 show #134's commit until it merges. #136 is about 390 hand-written lines.
**Questions for the human:** Should the funder export be limited to the donor's owner and the super admin instead of every member? Now it is every member, with contact details hidden from others.
**Shared-file changes requested:** none.

### Phase 3 lane C: messaging backend  (Sun 2026-11-15, MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #100 mail settings and reminders handoff note `shared` → PR #108 (merged) · #36 templates and drafts → PR #109 (merged) · #37 approval state machine → PR #110 (merged) · #38 email dry-run sender, SMS mark-sent, send history → PR #111 (merged) · #113 next-step timestamps use the app clock (CI fix on main) → PR #114 (merged) · #39 reminder digest → PR #128 · #126 bulk quarterly drafts → PR #129 (stacked on PR #128: both edit `app_messages.py` and the contract test).
**What changed:** Templates (thank-you, quarterly update, email and text) with built-in text stored on first use, `GET/PUT /templates` under `templates.manage`. Drafts are idempotent, never for do-not-contact donors, and never for employer-match gifts (D-127). Approve, edit (voids approval), cancel; approval stores who, when and a SHA-256 of subject and body. Send for email only, from `approved`, row-locked, hash re-checked; `dry_run` (default) records the send and makes no network call; `live` posts to Resend with the key from env; a provider failure sets `failed` with a short fixed error and is never retried. Texts expose a pre-filled `sms:` link; the owner clicks Mark sent. Every send writes the message record, a timeline interaction (`thank_you`/`update`, with `message_id` and `gift_id`) and a `message.send` audit entry without the words. Digest: board members only, counts only, one `digest_runs` row per click. Bulk quarterly drafts use lane A's `quarterly_due_for`.
**Gate** (acceptance tests 9 and 10, plus the extras you listed):
- [x] **Test 9**: `test_message_send.py::test_dry_run_thank_you_draft_approve_send_and_it_makes_no_network_call` (draft, approve, send; transport that fails if used saw 0 requests); editing after approval returns it to draft: `test_message_approval.py::test_editing_an_approved_message_returns_it_to_draft_and_clears_approval`; sending a draft is 409: `test_sending_a_draft_is_409_and_records_nothing`; the reminder clears: `test_sending_a_thank_you_clears_its_reminder` (only the thanked gift leaves the list).
- [x] **Test 10**: `test_digest.py::test_digest_dry_run_records_one_run_with_each_members_own_counts_only` (one run, Diana 2 and Sam 1 next steps, no donor names, no network call).
- [x] Double-send race: `test_two_simultaneous_sends_produce_one_send` (two threads, one send, one 409, one interaction, one audit row). Hash mismatch: `test_a_changed_body_is_refused_at_send_even_if_the_status_says_approved`. Do-not-contact, idempotent drafts, 403 for non-owners: `test_message_drafts.py`, `test_message_send.py::test_a_non_owner_cannot_send_or_mark_sent`. Database checks refuse an unapproved send: `test_the_database_refuses_sent_or_approved_without_an_approval`.
- [x] Lint, types, tests on the last branch: `uv run ruff format --check .` → "156 files already formatted"; `uv run ruff check .` clean; `uv run mypy app` → "no issues found in 110 source files"; `uv run pytest` → 622 passed. `npm run gen:api && npm run typecheck` clean after each route change.
- [ ] Not run: GitHub CI for the two open PRs, anything against Render or Neon, a real email (tests inject a transport; no real key is used).
**How to verify (exact steps):**
1. Merge PR #128, then PR #129, with merge commits. Render redeploys; no migrations in this lane.
2. **Render is in `live` mode with a real Resend key.** Only use donors whose email you own, or set `MESSAGING_MODE=dry_run` first.
3. Post-deployment test, on `https://cic-compass.onrender.com/api/docs` after logging in (or with curl and the session cookie and `X-CSRF-Token`): `GET /api/app/templates` shows four templates. Pick a donor you own, set their email to your own address, `POST /api/app/donors/{id}/messages` with `{"kind":"thank_you","channel":"email","gift_id":<gift>}` → 201 draft with a filled body; repeat the call → 200, same id. `PATCH /api/app/messages/{id}` with your own words, `POST .../approve` → `approved`; `PATCH` again → back to `draft`; approve again. `POST .../send` → `sent`, `provider_ref` starts with `re_` (live) or `dry-run-` (dry run); the email arrives only in live mode. `POST .../send` again → 409. `GET /api/app/donors/{id}/timeline` shows the message once; `GET /api/app/reminders` no longer lists that gift. `POST /api/app/messages/draft-quarterly` → drafts for your due donors; call twice, second says `skipped_existing`. `POST /api/app/digest/send` → one run; in live mode it emails board members counts only.
**Decisions made:** D-133, D-134 (below, also in DECISIONS.md). Also: a repeat draft request returns the open draft with 200 (201 only when created); a provider failure returns 200 with `status: failed` so the failed state is saved; approval is refused while `[EDIT: ...]` text from the default templates remains; drafting uses the donor's first name, else the display name.
**Known gaps:**
- No screens yet: drafts, approval and the digest button are API only until lane B's Phase 4 messaging UI.
- The digest email has no link to the app and no Reply-To; replies go to `MAIL_FROM`. The mail sender must be on a domain verified in Resend.
- Digest and send hit Resend one request at a time with a 10 second timeout, no queue.
- `GET /templates` creates the missing default rows on first view (a write in a GET, once).
- The first full-suite run on the CI-fix branch had two failures and one error in `test_message_approval.py` that did not repeat (re-run clean, file passes alone); cause not found.
- PR sizes over about 400 lines: #111 (about 580 including tests and generated files).
- Lapsed nudge and event invite templates are not built (later list).
**Questions for the human:** Should the digest mail include a link to the app (needs an `APP_BASE_URL` setting) and should messages carry a Reply-To?
**Shared-file changes requested:** none open. Merged with PR #108: `backend/app/settings.py` (`resend_api_key`, `mail_from`) and `docs/PLAN.md` (handoff note to lane A, also posted on #32). Touched outside lane C paths: next-step and interaction timestamps in `backend/app/repos/relationship.py`, `app/services/donors/contacts.py`, `app/routes/app_donors.py` and the timeline query in `app/repos/donors.py` (PR #114, lane C's own Phase 2 code).

### Phase 3 lane A: ownership, governance, reminders  (Sun 2026-11-15, morning MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #32 derived reminders → PR #118 · #29 manual and bulk reassignment → PR #119 · #30 member invites and deactivation → PR #121 (stacked on #118: its test reads Needs reassignment) · #31 governance scope and flatten → PR #122 (stacked on #119: its test reassigns after Flatten). No migrations and no shared-file changes.
**What changed:** Reminders are derived by query with an injected `today` (thank-you, quarterly, next step, needs reassignment) and cleared by the `messages` and `interactions` rows lane C already writes. Reassignment follows `policy.can(donor.reassign)`, needs an active target, and writes `owner_history` and an audit entry under the round-robin lock; the super admin can bulk-move a member's donors. Invites are one-time, 72 h, stored hashed, returned once; deactivation revokes sessions, moves no donors and refuses the super admin and self. Scope and Flatten are super-admin-only and audited; `superadmin.flatten` now also accepts the active super admin through `policy.can`.
**Gate:**
- [x] Acceptance 5 (deactivate: no donors move, Needs reassignment for everyone, manual reassignment in owner history): `test_members.py::test_deactivating_a_member_moves_no_donors_and_shows_needs_reassignment`, `test_reassign.py::test_flat_mode_any_member_reassigns_and_history_records_it`.
- [x] Acceptance 6 (own_only returns 403, after Flatten the member can): `test_reassign.py::test_own_only_blocks_other_members_donors_until_flattened`, `test_governance.py::test_scope_blocks_a_member_until_the_hierarchy_is_flattened`.
- [x] Acceptance 8, reminders half (a logged contact clears the quarterly reminder): `test_reminders.py::test_a_logged_contact_clears_the_quarterly_reminder`.
- [x] Lint and types on each PR branch: `ruff format --check .`, `ruff check .` and `mypy app` clean; full `uv run pytest` exits 0 on each branch (5 + 5 + 6 + 4 new tests); `npm run gen:api` and `npm run typecheck` clean after each route change.
- [ ] Not run: CI results on GitHub, the frontend lint/build, and anything against Render or Neon.
**Functions lane C can import** (`from app.services.reminders import ...`): `todo_for(db, actor, today, user_id)`, `counts_by_member(db, actor, today)` → `{user_id: ReminderCounts(thank_you_due, quarterly_due, next_step_due, needs_reassignment)}` for the digest, `quarterly_due_for(db, actor, today, user_id)` → `list[ReminderOut]` for draft-quarterly; also `needs_reassignment_list(db, actor, today)`.
**How to verify (exact steps):**
1. Merge #118, #119, #121, #122 in that order. #119, #121 and #122 each regenerate `openapi.json`, `types.ts` and the IMPLEMENTED set in `test_api_contract.py`, so expect small conflicts: take both sides, then run `cd backend && uv run python -m app.export_openapi ../frontend/src/api/openapi.json && cd ../frontend && npm run gen:api`.
2. Post-deployment test (flat mode, two members A and B, log in with the API docs page or curl with the CSRF header): `POST /members/invite {"email": "c@example.org"}` as A and open the returned `invite_url` token in `POST /auth/invite/{token}/accept`; `POST /members/{B}/deactivate` as A, then `GET /reminders/needs-reassignment` as A shows B's donors and B's old session gets 401; `POST /donors/{id}/reassign {"to_user_id": A}` and `GET /donors/{id}/owner-history` shows it. With a super admin (CLI `superadmin create`), `PUT /governance/scope {"reassign_scope": "own_only"}`, a plain member's reassign of another's donor returns 403, `POST /governance/flatten` then the same call returns 200.
**Decisions made:** D-132 (reassignment updates the target's `last_assigned_at`, as you asked). Also: do-not-contact donors get no thank-you reminder (MSG-8); quarterly ignores `system` interactions; `GET /reminders` lists the member's own reminders by urgency, then Needs reassignment; bulk move is guarded by `gov.set_scope` (active super admin) because the policy has no bulk action; invite and deactivate use `invite.create`; a member cannot deactivate themselves.
**Known gaps:**
- `invite_url` is `<request base URL>/invite/<token>`; lane B owns the accept page and may rename the path.
- The thank-you and update donor status chips (lane C's card query) still do not read these reminders.
- Open invites are not listed or revocable; a second invite for the same email just adds another one.
- Reminder queries run over all donors and are not paged (fine at about 1,000 donors; not measured on Neon).
- PRs #121 and #122 show their base PR's commits until it merges.
**Questions for the human:** none blocking.
**Shared-file changes requested:** none.

### Phase 2 lane A: ingest, dedupe, review and ownership (Sat 2026-11-14, report prepared 23:19 MST)
**Issues / PRs (merge commits, in this order):** #15 → PR #82 (merged; blank-row/header fixes included), #84 `shared` → PR #89 (merged), #16 → PR #98, #17 → PR #99, #18 → PR #101, #71 → PR #103, #102 → this `shared` documentation PR. Every PR targets `main`; humans merge.

**What changed:** The four CSV/XLSX adapters feed a read-only preview, then one commit transaction under advisory lock 4201. Commit revalidates identities, file hash, gift keys, programs and cutoff against current data. It saves one import row per nonblank physical source row, separate donation/match gifts, review items, donor identities, balanced ownership/history and audit. Batch history is durable; reversal soft-deletes its gifts and its created donors with no other live gifts, closes its open reviews and is audited. Review-created donors are included in reversal lineage. Anonymous attribution uses `review.decide`, preserves owners, applies the old-gift cutoff and adds the gift to the existing timeline without recording contact.

**Gate (local Docker Postgres only):**

- [x] Acceptance 1: `test_finished_importer_matches_manifest_and_acceptance_1_to_4` runs the actual upload/commit routes on spreadsheet → Zeffy → Benevity → generic. Exact manifest results: 225 donors, 19 review items/reasons, 531 valid gifts, 14 invalid rows/reasons, 13 anonymous Benevity gifts, and matching D-127 retention classes/cents. Benevity: 80 source rows, 91 gifts, 597500 donation cents + 101250 match cents = 698750 gross cents. Rows and cents reconcile independently.
- [x] Acceptance 2: the same integration test checks identical-file 409s plus shuffled and overlapping exports for all three gift sources: zero new gifts, no new donors/reviews and unchanged totals. Concurrent same-file commits produce one 200 and one 409. Stale previews revalidate gift keys and donor identity inside the lock.
- [x] Acceptance 3: fixture cross-source identities link; phone matches enter review; resolving a real imported review remembers its email for the next file. Separate review tests cover household conflicts, all gifts on one source row, audit and atomic rollback.
- [x] Acceptance 4: all 225 imported donors have owners, 75 per active member; inactive members get none. Existing-donor gifts preserve owners; a new donor fills the lightest member. Assignment order is first gift date then name, with oldest last-assignment/id tie-breaks under the lock.
- [x] Authorization: allow/deny, session and CSRF tests cover every implemented lane route. Review decisions and attribution check `review.decide`; import operations check `import.run`.
- [x] #18 full backend verification: `.venv/Scripts/ruff.exe check --no-cache .` → `All checks passed!`; `.venv/Scripts/mypy.exe app` → `Success: no issues found in 86 source files`; `.venv/Scripts/python.exe -m pytest -p no:cacheprovider --tb=short` → `618 passed, 2 skipped`.
- [x] #71 affected suites: `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/integration/test_gift_attribution.py tests/integration/test_import_commit.py tests/integration/test_identity_reviews.py tests/integration/test_api_contract.py --tb=short` → `151 passed, 2 skipped`; Ruff clean; mypy clean (87 files).
- [x] Final full backend run including #71: with both database URLs explicitly set to local Docker `cic_test`, `./.venv/Scripts/python.exe -m pytest -p no:cacheprovider --tb=short` → `623 passed, 2 skipped, 1 warning in 351.04s`. `./.venv/Scripts/ruff.exe check --no-cache .` → `All checks passed!`; `./.venv/Scripts/mypy.exe app` → `Success: no issues found in 87 source files`.

The two skips are the existing session and CSRF checks for the public invite-accept stub; no import, review, ownership or attribution test is skipped. The existing FastAPI/httpx deprecation warning remains. Core acceptance 1–4 passed before the Sat 23:00 MST target; the final attribution and full-lane verification finished after the target. No cut-list item has been applied. The shared #84 contract/types passed frontend generation, typecheck, lint and build; lane A's subsequent route-body changes leave the generated OpenAPI contract unchanged (tested).

**How to verify (exact steps):**

1. Merge the lane PRs in the order above. From the repo, start local Docker Postgres with `docker compose up -d db`. Use only local `cic_test` for both `TEST_DATABASE_URL` and `DATABASE_URL`; never use a shared/Neon database for tests.
2. In `backend`, run `uv run ruff check .`, `uv run mypy app`, and `uv run pytest`. For just acceptance 1–4: `uv run pytest tests/integration/test_import_commit.py -k finished_importer -v`. The full suite creates/migrates and truncates the local test database.
3. For human app verification after the code merges, log in and upload the four synthetic fixtures in manifest order. Check row/gift/split-cents summaries; commit each; re-upload; resolve one phone match; verify owner balance and unchanged owners for existing donors. Reverse a small test batch and check its durable history.
4. Attribute an anonymous gift to an existing donor. It leaves the unattributed list, appears in that donor's gift timeline, preserves the owner and creates one `gift.attribute` audit entry. Old gifts remain assumed thanked; employer matches still do not increase employee giving.

**Decisions made:** D-127 records CIC's explicit change to D-125: keep the match relationship for traceability and count it as org revenue, but exclude it from employee totals, lifetime giving, retention and pre-filled message amounts. Preview class counts are physical source rows, with separate gift counts and donation/match cents. No model or migration changes were needed in this lane.

**Lane C handoff:** After #17 and #18 merge, notify `#team-karma-js` that #73 can use `app.services.dedupe.reviews.candidates(db, actor, incoming)` and `app.services.ownership.assignment.assign_new(db, actor, donor, clock)`. Manual create should take `app.repos.ownership.lock(db, actor)` before candidate matching and hold it through creation, identity learning and assignment in one transaction. Manual donors must retain `created_via = manual` in lane C's repository. The team notification is pending those merges; it has not been sent.

**Known gaps:** Preview state is bounded process memory (20-minute TTL, 16 entries, 32 MiB); worker restart/eviction requires re-upload. Source layouts remain assumed where documented. Generic files without transaction IDs retain the documented split-file identical-gift limitation. #93 computed XLSX values/missing formula caches, #94 per-row control characters, #95 gift-date bounds, #96 scientific-notation amounts and #97 CSV Excel serial support are follow-ups explicitly requested in the #82 review, not implemented here. Message templates/reminders are later-phase work and must honor D-127; lane B owns the import/review/attribute UI. Deployed human acceptance remains pending; this agent did not change Render/Neon or run development/tests against a shared database.

**Questions for the human:** Approve the documentation push/PR actions when shown; review and merge the PRs, then perform human app verification. #71 was published after the approved full-suite condition passed. No next-phase work is authorized by this report.
**Shared-file changes requested:** #84 → PR #89 handled the summary contract, generated API files, donor/report credit queries, fixture expectations and D-127 documentation. #102 changes only this phase log and README, in a separate `shared` PR after lane code.

### Phase 2 lane A: CIC match-credit decision and summary contract (shared #84)
**Issues / PRs:** #15 → PR #82 and #84 → PR #89 are merged. The complete lane report above supersedes this shared-preparation checkpoint.
**What changed:** CIC decision D-127 supersedes employee credit in D-125. Employer matches remain separate flagged gifts with company payer and `:match` transaction suffix, and remain org revenue. Employee totals, lifetime giving, retention and pre-filled message amounts exclude employer matches. Donor linkage remains for traceability. Preview classes count physical source rows and expose separate gift counts, donation cents and match cents; rows and total cents reconcile independently. Fixture generator, manifest and independent resolver test change together; fixture file bytes remain unchanged.
**Gate:** Shared checks: backend `.venv/Scripts/ruff.exe check --no-cache .` clean; `.venv/Scripts/mypy.exe app` clean (70 files); with both database URLs explicitly set to local Docker `cic_test`, `.venv/Scripts/python.exe -m pytest -p no:cacheprovider` → 558 passed, 2 skipped. Includes deterministic fixture regeneration, independent manifest recomputation and match-credit regression tests. `python -m app.export_openapi ../frontend/src/api/openapi.json` and frontend `npm run gen:api`, `typecheck`, `lint`, `build` pass. Full Phase 2 acceptance tests 1–4 remain pending the importer.
**How to verify:** On local Docker Postgres, run backend Ruff, mypy and pytest; regenerate OpenAPI and frontend types, then run frontend typecheck, lint and build. The Benevity manifest must retain 80 rows, 91 valid gifts, 597500 donation cents and 101250 match cents; org gross stays 698750 cents.
**Decisions made:** D-127, explicitly requested by CIC through the lane A engineer.
**Known gaps:** Message routes are still Phase 3 stubs; lane C must apply D-127 when filling message amounts. Board members review and edit drafts before approving and sending. Lane B must render the new summary fields in its import screen. Full importer/manifest integration and acceptance tests 1–4 await #17/#18.
**Questions for the human:** Push/PR approval required by ENGINEERING section 7 once the shared commit is ready.
**Shared-file changes requested:** #84: import-summary schema and generated OpenAPI/TS types; donor/report queries; SRS, data model, decisions, import formats and phase log; fixture generator/manifest and tests. No models or migrations change.

### Phase 2 lane C: read API, MCP, donor API  (Sat 2026-11-14, about 18:30–21:30 MST)
**Issues / PRs (merge in this order, with "Create a merge commit"):** #24 API keys → PR #77 `shared` (merged) · #25 `/api/v1` endpoints → #78 (merged) · #72 donor list, detail, timeline, unattributed → #79 (merged) · #74 contact log and next step → #80 (merged) · #26 report queries → #81 (merged) · #27 MCP server → #83 · #28 API guide → #85 · #87 `apikey` CLI → PR #90 · #88 audit contact and next-step actions → PR #91. #73 donor create, edit, delete and manual gift → two PRs, built after lane A's #17 and #18 merged.
**What changed:** API keys (`cic_live_` + 32 random bytes, SHA-256 only, shown once, scope, last used, revoke) with the key-auth dependency and a 60 per minute per key limit. Six `/api/v1` read endpoints (`summary`, `retention`, `totals/by-period`, `totals/by-program`, `totals/by-board-member`, `activity/recent`) plus `health`, all aggregates in USD cents with `as_of`. The app's Reports page and `/api/v1` share one set of queries. Donor list (My/All, search, filters, pagination), detail, timeline, unattributed gifts; contact log and next step. A read-only stdio MCP server with six tools in `mcp_server/`, its own lockfile and CI job. `docs/API_GUIDE.md`. `python -m app.cli apikey {create,list,revoke}`.
**Gate** (Phase 2 gate for lane C: acceptance tests 7, 12, and 11 for retention; 1 to 4 belong to lane A):
- [x] **Test 7**, another member sees history but not email, phone or notes: `tests/integration/test_donor_read_api.py::test_other_member_sees_history_but_not_contact_details` (also checks the timeline and email search); acting on that donor returns 403: `test_contact_and_next_step.py::test_other_member_cannot_act_on_a_donor_they_do_not_own` (nothing is written).
- [x] **Test 12**, valid key returns aggregates, no key, wrong key and revoked key return 401, wrong scope 403, 61st request 429 with `Retry-After`: `test_v1_aggregates.py` (`test_no_key_wrong_key_and_revoked_key_get_401`, `test_wrong_scope_gets_403`, `test_rate_limit_is_60_per_minute_per_key_with_retry_after`). No donor PII in the schema: `test_openapi_for_v1_has_no_donor_pii_fields` walks the `/api/v1` OpenAPI document and fails on any donor name, email, phone, note or id field; `test_responses_contain_no_donor_pii` checks real responses.
- [x] **Test 11**, retention classes match the manifest, checked ahead of lane A's importer: `test_reports.py::test_retention_matches_the_fixture_manifest` loads the donors and gifts that `test_fixtures.py` resolves independently and gets 33 new, 10 reactivated, 25 increased, 18 same, 31 decreased, 40 lapsed as of 2026-11-15, with matching cents. To be repeated through the real importer once lane A lands.
- [x] Lint, types, tests: `uv run ruff check . && uv run ruff format --check . && uv run mypy app` clean (70 files); `uv run pytest` 551 passed, 2 skipped on the audit branch (559 on the CLI branch) at the last run; `cd mcp_server && uv run pytest` 20 passed, ruff and mypy clean; `npm run gen:api && npm run typecheck` clean after each route change.
- [x] MCP works end to end (run by hand, local Docker database): the server over stdio listed the six tools and returned data for all six against a local backend; a wrong key gave "The API key was rejected".
- [x] Guide examples run: every `curl` in `docs/API_GUIDE.md` was run against a local backend; example responses are the real output, including the 429 `retry-after` header and the login, create, list and revoke key flow.
- [x] Speed (NFR-7), local Docker database, 1,000 donors and 5,000 gifts, in-process test client: donor list median 146 ms (slowest run 387 ms, cold), search 69 ms, status filter 144 ms, donor detail 51 ms, timeline 46 ms, retention 164 ms, report summary 303 ms. Not measured against Neon over the network.
- [x] **#73** manual donor create (duplicate warning with candidates, round-robin owner), edit, soft delete and manual gift: `tests/integration/test_donor_writes.py` (8 tests) and `test_manual_gifts.py` (6 tests), kept to the MVP cases.
**How to verify (exact steps):**
1. Merge the open PRs with merge commits, in this order: #83 (MCP), #85 (guide), #90 (CLI), #91 (audit), then this report.
2. `docker compose up -d db`, `cd backend && uv run alembic upgrade head && uv run python -m app.cli setup`, `uv run uvicorn app.main:app`.
3. Create a key: `uv run python -m app.cli apikey create --name Dashboard --email <member email>`. Then `curl -H "Authorization: Bearer <key>" localhost:8000/api/v1/totals/by-program` returns 200; without the header 401. `apikey revoke <id>` then the same call returns 401.
4. Log in as two different members (private window). The second opens `GET /api/app/donors?scope=all` and a donor owned by the first: gift history and timeline appear, email, phone and notes are null with `contact_via` set; `POST /api/app/donors/{id}/interactions` returns 403.
5. Follow `docs/API_GUIDE.md` steps 1 and 2 on the deployed URL; for Claude Desktop follow `mcp_server/README.md`.
6. After lane A's importer lands: import all fixtures, then `GET /api/v1/retention?as_of=2026-11-15` and compare with `fixtures/manifest.json`.
**Decisions made:** D-128 (rate limit in memory), D-129 (notes are a contact detail). Also: the v1 retention response carries `retention_date` beside `as_of` because API.md used one name for two things; the stored key prefix is 13 characters (`cic_live_` + 4), not 8; `new` means first linked gift in the last 30 days; the CLI `apikey create` records the member it is for (`--email`). For #73: creating a donor uses lane A's `ownership.assign` with the `import.run` policy action (any member), and a manual gift dated before the import cutoff is marked `assumed_thanked` like imported history.
**Known gaps:**
- **Manual gift `note` is refused** (400 "Gift notes are not stored yet") when non-empty: the gifts table has no note column, gift history is visible to every member (D-104) and a note may hold personal details, and logging it as a contact note would wrongly clear the quarterly reminder. Options: a migration adding an owner-only gift note, or drop `note` from the contract. Donor merge (`POST /donors/{id}/merge`, DED-7) still answers 501 (not scheduled).
- `thank_you_due` and `update_due` donor statuses and every `open_reminders` count are missing or 0 until the reminders service (lane A, Phase 3).
- The rate limit is per process and in memory: exact on Render's single worker, reset by a restart, not shared across workers (D-128).
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
