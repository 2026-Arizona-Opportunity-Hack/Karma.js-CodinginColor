# CIC Compass: Software Requirements Specification (v3, FastAPI)

Team Karma.js · Opportunity Hack Fall 2026 · Coding in Color (CIC) · Problem 2: Donor & Funder Relationship Platform
Sources of truth, in order: (1) the official CIC problem brief, (2) what CIC's board members and mentors told us on Saturday, (3) this document. Conflicts are logged in `docs/DECISIONS.md`.

---

## 1. Problem

CIC receives gifts through Zeffy, AZ Gives, United Way and Benevity. Today there is no automation: a board member occasionally logs into a platform, exports the data by hand and acts on it. Donors and funders live in one spreadsheet. Nobody can see in one place who gave, when, how much, or when they were last contacted, and follow-ups get lost.

**CIC's stated minimum (Saturday conversation):**
1. A central, structured datastore.
2. CRUD screens for easy access.
3. A reminder system so every donor is followed up at least every quarter.

**What judges score (brief, Problem 2 P0):** one deduped donor table from the spreadsheet plus Zeffy and Benevity exports; round-robin board-member ownership; donor timeline; follow-up reminders and quarterly touches; retention view; templated thank-you with human approval and send history; one-click funder export; key-authenticated read API. Judging categories from the repo README: **Scope, Documentation, Polish, Security**, plus a separate **Accessibility** prize.

**Principle:** build the minimum that works end to end, then improve. Every P0 ships in its smallest correct form before any P1 starts.

## 2. Users and roles

The hierarchy is **flat by default**: all board members are equals.

| Role | Who | Notes |
|---|---|---|
| `board_member` | CIC board members, including Diana | Individual login. Owns a slice of donors. |
| `super_admin` | Optional, at most one person | A board member with extra powers. Created only by the setup command, never from the app. Cannot be deleted. States: `active` or `dormant`. |
| `api_client` | CIC's org dashboard, an MCP client | API key, not a person. Read-only, aggregated data only. |

There is no separate staff role this weekend. Donors are stakeholders, not users.

## 3. Scope

### 3.1 MVP (P0, must demo Sunday)

| Area | Summary | Req IDs |
|---|---|---|
| Auth and accounts | Individual logins, invites, sessions, setup command | AUTH |
| Governance | Flat by default, optional super admin, flatten, reassignment scope | GOV |
| Ingestion | Upload CSV/XLSX exports, transform, load, import summary | ING |
| Dedupe | Gift-level idempotency, donor identity resolution, review list | DED |
| Ownership | Owner on donor, round-robin for new donors, manual reassignment, departures | OWN |
| Donor CRUD and visibility | My/All toggle, donor detail timeline, manual entry | DON |
| Reminders | Derived reminders, To-do list, email digest on demand | REM |
| Donor messages | Templates, drafts, approval, send, send history | MSG |
| Reporting | Summary, retention view, funder export | RPT |
| Read API and MCP | Key-authenticated aggregated API, read-only MCP server | API |
| Non-functional | Security, accessibility, cost, docs | NFR |

### 3.2 Improve-later list (only after every P0 is verified)

| Order | Feature | Brief mapping |
|---|---|---|
| 1 | **Lapsed-donor radar**: lapsed list with a drafted nudge per owner | P1 (our committed P1 pick) |
| 2 | **Events-aware next steps**: an events list (Day of Compute, camps); "Invite to event" creates a next step with the event date and a drafted invite | P1 / beyond-scope pick; merges the "notable days" idea |
| 3 | Zeffy API pull job (replaces manual Zeffy upload); other platforms stay on upload | Beyond scope |
| 4 | AI-drafted messages from donor notes and history via the OHack AI gateway, behind a flag, human approves | P1 "AI-drafted donor updates" |
| 5 | Milestone messages ("we passed $X thanks to you"), holiday touch reminders | Ours |
| 6 | Dashboard charts, likelihood-to-give score | P2 |
| 7 | Debrief to action (note becomes contact record, next step and draft) | P1 |

**Non-goals:** a general CRM; replacing Zeffy or the other platforms; automatic sending to donors; merging people by name similarity; real donor data anywhere in the repo; PDF or plain-text parsing; Problem 1 features.

---

## 4. Functional requirements

Priority: **M** = must (P0), **S** = should (P0 thin version acceptable), **C** = could (later list).

### 4.1 AUTH: accounts and sessions

| ID | Requirement | Pri |
|---|---|---|
| AUTH-1 | Every person has an individual account (email + password). No shared accounts or passwords. Passwords hashed with Argon2id. | M |
| AUTH-2 | Sessions use a random token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie; the server stores only its SHA-256 hash; idle expiry 12 h, absolute 7 days; logout revokes. | M |
| AUTH-3 | A setup command (`python -m app.cli setup`) creates the first board members from a local, git-ignored file or prompts, prints one-time passwords locally, and optionally creates the super admin. | M |
| AUTH-4 | Adding a board member in the app is by **invite link** (one-time, expires 72 h, stored hashed). Who can invite follows GOV-4. | M |
| AUTH-5 | All state-changing requests from the web app require a CSRF token (double-submit) in addition to the session cookie. | M |
| AUTH-6 | Login is rate-limited (5 failures per 15 min per email and per IP) with a generic error message. | M |
| AUTH-7 | Deactivated users cannot log in; their sessions are revoked immediately. | M |

### 4.2 GOV: governance and super admin

| ID | Requirement | Pri |
|---|---|---|
| GOV-1 | Default mode is **flat**: no super admin; every active board member has equal permissions. | M |
| GOV-2 | At most one super admin. It is created, re-activated or transferred **only** by the setup command run by whoever controls the deployment. No in-app path grants super admin. | M |
| GOV-3 | The super admin account cannot be deleted. It can be deactivated (no login) only by the setup command. | M |
| GOV-4 | Setting `reassign_scope` = `anyone` or `own_only`. In flat mode it is fixed to `anyone`. With an active super admin, only the super admin can change it. Inviting members, editing templates and programs, and managing API keys are open to all members in flat mode and super-admin-only when a super admin is active. | M |
| GOV-5 | **Flatten**: an active super admin can click "Flatten hierarchy". The role becomes `dormant`, `reassign_scope` becomes `anyone`, and the super admin acts as a regular board member. Re-activation requires the setup command. | M |
| GOV-6 | Break-glass: the setup command can set the role dormant, transfer it, or deactivate the account when the super admin is unavailable. | M |
| GOV-7 | Every governance change (created, flattened, re-activated, transferred, deactivated, scope changed) writes an audit entry with actor and time. | M |

### 4.3 ING: ingestion (upload, transform, load)

| ID | Requirement | Pri |
|---|---|---|
| ING-1 | Any board member can upload a file (CSV or XLSX, max 5 MB, by extension **and** content sniffing). Anything else is rejected with a friendly message. | M |
| ING-2 | The user picks the source: **CIC donor spreadsheet** (donor list), **Zeffy payments export**, **Benevity disbursement report**, or **Generic gifts template** (used for AZ Gives, United Way and anything else). Each source has an adapter that maps columns to the normalized shape. | M |
| ING-3 | Column layouts for Zeffy and Benevity are modelled on their publicly documented formats (Zeffy API payment/contact/campaign objects; Benevity's reporting glossary). Each adapter records where its columns came from in `docs/IMPORT_FORMATS.md`, marked `assumed` until a real CIC file is seen. | M |
| ING-4 | Import is two-step: **preview** (parse, validate, dedupe, classify every row) then **commit** (single DB transaction). Nothing is written before commit. | M |
| ING-5 | The preview and saved batch show an **import summary**: physical rows read = new + already imported + needs review + invalid source rows (including donor-only spreadsheet rows). Each class shows a separate gift count, donation cents, employer-match cents and combined gross cents (D-127). Anonymous rows are a subset of new rows. Reconcile both physical rows and total cents exactly or block commit. Show new donors and donors matched. | M |
| ING-6 | Invalid rows (bad date, non-numeric amount, non-USD, missing amount) are listed with a reason. No row is dropped silently. | M |
| ING-7 | Each gift gets a program from an editable `source_program_map` (for example Zeffy campaign "Summer Camp 2026" to Summer Camp). Unmapped values go to **General** and are listed in the preview. | M |
| ING-8 | The CIC spreadsheet import creates or updates **donors only** (people, organizations, funders). Gifts come only from platform files. | M |
| ING-9 | On commit, new donors are assigned owners (OWN-2) inside the same transaction. | M |
| ING-10 | Batch history page: who uploaded what, when, counts. A batch can be reversed (soft-deletes its gifts; donors it created with no other gifts are soft-deleted; audited). | S |
| ING-11 | Gifts older than the import cutoff (default 60 days before the import date) are marked `assumed_thanked` so a history backfill does not create hundreds of thank-you reminders. | M |

### 4.4 DED: dedupe

| ID | Requirement | Pri |
|---|---|---|
| DED-1 | **Same file again**: an upload whose SHA-256 matches a committed batch for the same source is blocked with "already imported on <date> by <name>". | M |
| DED-2 | **Same gift again** (re-upload, shuffled rows, overlapping date ranges): every gift has a deterministic `row_key` (see DATA_MODEL 3.1). A row whose key already exists is classified `already_imported` and not inserted. Re-importing never changes totals. | M |
| DED-3 | **Same person across sources**: identity resolution in this order: (1) exact platform ID already linked, auto-link; (2) exact normalized email, auto-link unless the names conflict; (3) exact normalized phone, or same normalized name plus employer, goes to **review**; (4) no candidate, new donor. Never auto-link on name alone. | M |
| DED-4 | **Review list**: each item shows the incoming record and candidates side by side. Decisions: link to donor X, create new donor, mark anonymous. A decision remembers the identity (email, platform ID) so the same person auto-links next time. Audited. | M |
| DED-5 | Gifts waiting for review are saved but not counted in donor totals, and their donor is not assigned an owner until resolved. | M |
| DED-6 | **Manual entry**: creating a donor runs DED-3 first and warns "possible existing donor" with a link before allowing create. | M |
| DED-7 | **Merge** two donors: gifts, interactions, messages and identities move to the surviving record; the owner of the **older** record is kept; audited. | S |
| DED-8 | Anonymous gifts (for example Benevity rows without donor details) are kept, attributed to no donor, and shown on an "Unattributed gifts" list. They count in org totals. | M |

### 4.5 OWN: ownership and reassignment

| ID | Requirement | Pri |
|---|---|---|
| OWN-1 | Ownership belongs to the **donor**, never the gift. A new gift from an existing donor never changes the owner. | M |
| OWN-2 | **Round-robin** for new donors only: assign to the active board member with the fewest owned active donors; ties by oldest `last_assigned_at`, then lowest id. Runs inside the import or create transaction with a lock so concurrent imports cannot unbalance. Starting from balanced loads, owned counts across active members differ by at most 1 after any import (manual reassignments may unbalance loads; round-robin then fills the lightest first). | M |
| OWN-3 | **Manual reassignment** per `reassign_scope`: `anyone` lets any board member reassign any donor to any active member; `own_only` lets a member hand off only their own donors; an active super admin can always reassign any donor and bulk-move all donors from one member to another. | M |
| OWN-4 | Every ownership change writes `owner_history` (from, to, by, method, reason, time) and an audit entry. History is visible to all board members on the donor page. | M |
| OWN-5 | **A board member leaves**: deactivation does **not** reassign donors. Their donors stay assigned, marked "owner inactive", and appear on a shared **Needs reassignment** list at the top of every member's dashboard until reassigned by hand. Their reminders keep showing on that list. | M |
| OWN-6 | Round-robin skips inactive members. | M |
| OWN-7 | The super admin can own donors like any board member. | M |

### 4.6 DON: donor CRUD and visibility

| ID | Requirement | Pri |
|---|---|---|
| DON-1 | **My donors / All donors** toggle. Default My donors. | M |
| DON-2 | Every board member can see every donor's **gift history and timeline**, owner and status (decision D-104). | M |
| DON-3 | **Contact details** (email, phone) are visible to the donor's owner and an active super admin only. Others see "Contact via <owner>". | M |
| DON-4 | Actions on a donor (log contact, set next step, draft, approve or send a message) are allowed for the **owner** and an active super admin only. Reassignment follows OWN-3. | M |
| DON-5 | Donor card (list item): name, total given (12 months and lifetime), last gift, last contact, next step and due date, owner, status chips (new, thank-you due, update due, lapsed, owner inactive, do not contact). Tapping expands to the last 5 gifts. | M |
| DON-6 | Donor detail page: header with actions; one **timeline** mixing gifts, messages sent, logged contacts, notes, next steps and owner changes, newest first. | M |
| DON-7 | Create and edit donors manually (person, organization, funder). Fields kept minimal: name, organization or employer, email, phone, kind, do-not-contact flag, notes. | M |
| DON-8 | Add a gift manually (for example a check): date, amount, program, source `manual`, optional note. Gets a `row_key` like any other gift. | M |
| DON-9 | Log a contact in 3 taps or fewer on a 390 px screen: kind (call, text, email, meeting, note), optional note, date defaults to today. | M |
| DON-10 | Next step: one open next step per donor with a title and due date. Completing it logs an interaction. | M |
| DON-11 | Search donors by name, email, organization; filter by owner, status, program. Soft delete only (admin restore later). | M |
| DON-12 | Any bulk export of donor-level data writes an audit entry and neutralizes spreadsheet formulas (cells starting `=`, `+`, `-`, `@`). | M |

### 4.7 REM: reminders

Reminders are **derived from data, never stored**, so re-imports cannot duplicate them and doing the action clears them automatically.

| ID | Requirement | Pri |
|---|---|---|
| REM-1 | **Thank-you due**: a received gift (not anonymous, not `assumed_thanked`, not yet thanked) is due 2 days after gift date for a donor's first gift, 7 days otherwise. Cleared by a sent thank-you message for that gift or a logged contact of kind `thank_you`. | M |
| REM-2 | **Quarterly touch due**: no sent message and no logged contact for the donor in the last 90 days. Cleared by either. Donors flagged do-not-contact are excluded. | M |
| REM-3 | **Next step due / overdue**: open next step due within 3 days, or past due. | M |
| REM-4 | **Needs reassignment**: donor owned by an inactive member (OWN-5). Shown to everyone. | M |
| REM-5 | **To do** list at the top of the dashboard: the user's own reminders, most urgent first, each with one action (Draft thank-you, Draft update, Log contact, Open next step, Reassign). | M |
| REM-6 | **Email digest**: one email per board member summarizing their open reminders with a link to the app. Never sent to donors. Sent only when a person clicks **Send reminder digest** (flat mode: any member; super admin active: super admin). Uses MSG-6 send modes; default dry-run. | M |
| REM-7 | Thresholds (2, 7, 90 days, cutoff 60) are settings, editable per GOV-4. | S |
| REM-8 | Open question for organizers: does an internal reminder email count under the brief's "every outbound message or reminder is drafted by the system and sent by a human"? If they say no, a scheduled weekly digest is a later change. | Note |

### 4.8 MSG: donor messages

| ID | Requirement | Pri |
|---|---|---|
| MSG-1 | Templates: **thank-you**, **quarterly update** (P0); lapsed nudge, event invite (later). Merge fields: donor first name, gift amount, gift date, program, owner name, org name. Pre-filled amounts use employee donations only, excluding employer matches (D-127); board members may edit the amount using donation-only dashboard/reminder data. Editable per GOV-4. | M |
| MSG-2 | The system creates **drafts** from templates when the owner clicks a reminder action, or in bulk with "Draft quarterly updates for my due donors" (idempotent: never two open drafts of the same kind for the same donor). | M |
| MSG-3 | State machine: `draft → approved → sent`, plus `sent_manually`, `cancelled`, `failed`. Only a human approves. Editing an approved message returns it to `draft`. The server rejects send from any state but `approved`. Enforced in code **and** by a database check. | M |
| MSG-4 | Approve and send are separate clicks by the owner (or active super admin). The body hash at approval must equal the body at send. | M |
| MSG-5 | Channels: **email** via a mail provider over HTTP; **text** via a pre-filled `sms:` link, then "Mark sent". | M |
| MSG-6 | `MESSAGING_MODE` = `dry_run` (default; records the send, delivers nothing) or `live` (needs provider key in env). The UI shows a visible "Dry run" badge. | M |
| MSG-7 | Every send writes send history (who, when, channel, mode, provider reference), a timeline interaction, and an audit entry; it clears the matching reminder. | M |
| MSG-8 | Do-not-contact donors cannot get drafts. | M |

### 4.9 RPT: reporting

| ID | Requirement | Pri |
|---|---|---|
| RPT-1 | Dashboard summary for all members: totals this month, quarter, 12 months; by program; by board member (owned donors' giving); counts of open reminders. | M |
| RPT-2 | **Retention view**: rolling last 12 months versus the previous 12 (calendar year as an option). Classes: new, increased, same, decreased, lapsed, reactivated. Counts, dollar movement, donor lists with drill-down. Shows the "as of" date. Employee giving, donor totals and lifetime giving exclude employer matches; org revenue includes them (D-127). | M |
| RPT-3 | **Funder export** (one click, per funder or donor): gift history by program and period plus funded outcomes, as printable HTML and CSV. Outcomes come from a small `program_outcomes` table entered by hand or CSV (stands in for Problem 1 data). | M (thin) |

### 4.10 API: read API and MCP

| ID | Requirement | Pri |
|---|---|---|
| API-1 | Read-only REST under `/api/v1`, authenticated by API key (`Authorization: Bearer cic_...`). Keys are shown once, stored hashed, scoped, revocable, with last-used time. Managed per GOV-4. | M |
| API-2 | Responses are **aggregates only**: no donor names, emails, phones, notes or ids. Board member display names are allowed (aggregation key). | M |
| API-3 | Endpoints: summary, by period, by program, by board member, retention, recent activity (see `docs/API.md`). | M |
| API-4 | Rate limit 60 requests per minute per key; 401 for missing, wrong or revoked key; 403 for scope mismatch. | M |
| API-5 | OpenAPI is generated by FastAPI; a human docs page with curl examples lets CIC's dashboard owner connect without us. | M |
| API-6 | **MCP server** (separate small package `mcp_server/`) exposes the same read endpoints as read-only tools; it calls the REST API with a key from its own env. No write tools. | S |
| API-7 | All writes happen only through the logged-in web app (session + CSRF). The app's internal endpoints live under `/api/app/*` and are not part of the public contract. | M |

---

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 Security | Server-side authorization in one policy module; every route checked; IDOR tests for donor access; secrets only in env; `.env` never committed (repo hook enforces); security headers (CSP, HSTS, X-Content-Type-Options, frame-ancestors none); input validated with Pydantic; uploads size and type checked; SQL only via SQLAlchemy parameters. |
| NFR-2 Audit | `audit_log` for logins, governance, imports, merges, reassignments, approvals, sends, exports, key changes. Append-only from the app. |
| NFR-3 Data minimization | Store only: names, organization or employer, email, phone, gift facts, notes. No addresses, no card or bank data. Synthetic data only in the repo. |
| NFR-4 Accessibility | Lighthouse accessibility 95+ on every main page; full keyboard path through import, review, log contact, draft, approve, send; visible focus; labels; 4.5:1 contrast; works at 390 px. |
| NFR-5 Cost | Hosting within $20/month plus $250 one-time. Plan: one Render Starter web service (~$7/month) serving API and built frontend; Neon Postgres free plan. Final numbers and plan terms in `docs/COSTS.md`. |
| NFR-6 Time | Business time zone `America/Phoenix`; gift dates are date-only; money in integer cents, USD only. An injectable clock for tests. |
| NFR-7 Performance | Donor list and search under 300 ms on 1,000 donors and 5,000 gifts. Import of 2,000 rows previews in under 10 s. |
| NFR-8 Docs | README (what, run, live link, demo link), `docs/` set, OpenAPI, runbook, handoff checklist. One GitHub Issue per task, closed by its PR. |
| NFR-9 Operability | `python -m app.cli` commands: `setup`, `seed-demo`, `reset-demo` (only when `DEMO_MODE=true`), `superadmin <action>`. Health check `/healthz`. |

## 6. Stack (locked)

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, psycopg 3, argon2-cffi, openpyxl, httpx |
| Frontend | React + Vite + TypeScript, React Router, TanStack Query, Tailwind CSS, Radix primitives where needed |
| Database | PostgreSQL 16 (Neon in production, Docker locally) |
| Tests | pytest (+ httpx test client), Playwright + axe-core, Lighthouse CI |
| Deploy | One Docker image on Render: FastAPI serves `/api/*` and the built SPA |
| MCP | Python MCP SDK, stdio transport, in `mcp_server/` |

## 7. Acceptance tests (run on the deployed URL before the freeze)

1. Import the spreadsheet, Zeffy and Benevity fixtures; summaries reconcile and match `fixtures/manifest.json`.
2. Re-upload the same file (blocked), a shuffled copy and an overlapping copy (0 new gifts); totals unchanged.
3. Cross-source duplicate donors auto-link on email; a phone-only match lands in review; resolving it links the gift and remembers the identity.
4. After import every donor has an owner; counts differ by at most 1; a gift from an existing donor keeps its owner; a new donor goes to the member with the fewest.
5. Deactivate a member: no donors move; they appear on Needs reassignment for everyone; manual reassignment works and shows in owner history.
6. Scope: with `own_only` (super admin active) a member cannot reassign another member's donor (API returns 403); after Flatten, they can.
7. All donors view shows another member's gift history but not their donor's email or phone; acting on that donor returns 403.
8. Log a contact in 3 taps at 390 px; it appears on the timeline and clears the quarterly reminder.
9. Draft, approve, send (dry run) a thank-you; editing after approval returns it to draft; sending a draft returns 409; the reminder clears.
10. Digest button records one dry-run digest per member with their own reminders only.
11. Retention classes match the manifest.
12. API: valid key returns aggregates; no key, wrong key, revoked key return 401; response schema contains no donor PII fields.
13. Lighthouse accessibility 95+ on main pages; keyboard-only completes the core path.

## 8. Assumptions and open questions

| Topic | Assumption we build on | Ask |
|---|---|---|
| Export formats | Modelled on public Zeffy and Benevity docs; generic template for the rest | CIC can send header rows later; adapters change, nothing else |
| CIC spreadsheet | One row per donor (person, organization or funder) | Confirm |
| Programs | Seed: AI Academy, K12 Program, Summer Camp, Day of Compute, General; Zeffy campaign name maps to program | Confirm list |
| Reporting year | Rolling 12 months; calendar optional | Fiscal year? |
| Internal digest email | Sent by a human click | Organizers: does it count as a "reminder"? |
| Contact details | Owner and active super admin only | Confirm |
| Mail provider | Dry-run default; live provider chosen in Phase 0, cost recorded | CIC sending domain |
