# #33 — Dashboard To-do & Needs reassignment

Implemented on `lane-b/33-dashboard-todo`, frontend only. Generated contracts,
dependencies, backend and deployment unchanged. The user approved the size-limit
exception and local commit; pushing/opening a PR still requires Engineering §7
approval. This does not implement #34/#35 or claim the full Phase 3B gate.

## Contract and behavior

Verified merged dependencies: #19 → PR #120, #20 → #124, #21 → #140,
#22 → #132, #23 → #125; backend PRs #118, #119, #121, #122.

Inspected generated `ReminderOut`/`ReminderListOut`, `app_ownership.py`, reminder
service and repository. `GET /api/app/reminders?scope=mine` already includes every
Needs reassignment record. Preserve server order, due dates and overdue flags;
derive only visible counts. No new priority scores or locally completed reminders.

Actor-keyed TanStack Query uses the existing API client, abort signal and
`reminders` invalidation prefix. Existing successful contact, next-step and donor
entry mutations invalidate it. Mount/focus/reconnect, one-minute foreground refresh
and manual refresh keep derived data current. Errors hide cached rows, including
after 403, and reuse the existing retry/sign-in state.

Links focus donor contact, next step, gift history or ownership. The dossier checks
current capabilities before writes. No permission is inferred from queue visibility.
Drafting has no implemented UI; clear availability notes accompany gift review or
contact logging. Reassignment is view-only pending #34. Ordinary contact logging
does not pretend to clear gift-linked thank-you reminders.

## Design and visual QA

People lead the page, with commitments and ownership as their context. Warm canvas,
forest controls, copper rules and Georgia headings reuse existing tokens. Ruled
rows give the dashboard the rhythm of a working ledger. Backend overdue flags
provide calm urgency without a separate scoring system. Routine stewardship and
shared ownership exceptions have separate queues. Category controls and full-width
mobile actions support a quick keyboard or touch path. Loading, empty and failed
views reuse established workspace components.

Evidence scan: [Attio](https://attio.com), [Linear](https://linear.app),
[Stripe](https://stripe.com) and the shipped nonprofit CRM
[Sapling case study](https://www.vandangohil.com/reports). Adapted record-first
hierarchy, restrained controls and action-oriented workflows; no assets/code copied.

Screen anatomy: heading/date → queue jump links/counts → own reminders in server
order with filters → shared reassignment queue. Rows identify donor, category,
owner, entity reference, due status/date and one navigation action. Keyboard follows
document order; links move focus into the dossier. At 390px, rows stack with
full-width actions. Empty categories differ from no reminders; failures offer retry.

Inspected rendered screenshots at 390×844, 768×1024 and 1440×900. The polish pass
added queue jump links/counts near the top so reassignment remains discoverable
below a long To-do list. Verified long names, dates, wrapping, no horizontal page
overflow, keyboard focus, reduced motion and a 720×450 layout equivalent to 200%
desktop zoom. Actual browser zoom and screen-reader/axe audits were not performed.

Screenshots (synthetic records only):

- [390px real backend](390-live.png), [768px real backend](768-live.png),
  [1440px real backend](1440-live.png)
- [Server-confirmed contact clearing](390-live-contact-cleared.png)
- [Loading](loading.png), [empty](390-empty.png), [403](390-forbidden.png)
- [Long donor name](390-long-name.png), [zoom-equivalent](720-zoom-equivalent.png)

## Executed verification

From `frontend/`:

- `npm run typecheck`, `npm run lint`, `npm run build`: passed.
- Changed TS/TSX/CSS/JS/package/QA Markdown files, `prettier --check`: passed.
- `npm run test:ledger`: 9 passed; `npm run test:entry`: 5 passed;
  `npm run test:updates`: 3 passed.
- `npm run test:dashboard`: passed. Synthetic network-boundary coverage: categories,
  counts/order, gift/next-step/ownership navigation, cached-record focus, keyboard
  filtering, failed 403 contact without completion, successful contact/refetch,
  stale-cache hiding on 401/403/500/501, retry, loading, empty/filtered-empty,
  1/205 records, long names, responsive layouts and reduced motion.
  Chrome ignores only its exact cancelled-interception protocol error caused by
  React StrictMode aborts/navigation; other protocol/runtime errors fail QA.
- `npm run test:dashboard:live`: passed without interception. Fresh local PostgreSQL
  database `cic_33_8519807ce4`, migrated through head, FastAPI on 127.0.0.1:8000.
  Authenticated with a synthetic member; checked all four categories and all three
  widths; logged contact through the sheet; confirmed quarterly reminder absent
  from both API response and refreshed dashboard.
- `npm run test:detail`, `npm run test:contact`: existing browser regressions passed.
  Their regenerated #20/#23 screenshots were discarded to keep #33 focused.

Reproduce with Node 22+, installed frontend dependencies and local Chrome
(`CHROME_PATH` supported). Start Vite: `npm run dev -- --host 127.0.0.1`.
For live QA, first run
`../backend/.venv/Scripts/python.exe tests/dashboard-local.py` from `frontend/`.
It uses explicit 127.0.0.1 PostgreSQL defaults, creates a unique database, migrates,
seeds synthetic records and starts FastAPI. It never reads a hosted database URL.
Session credentials stay in ignored `.test-build/33-session.json`. Each live run
requires a fresh seed because logging contact changes the reminder. The isolated
database is retained for inspection.

Known limits: drafting UI and reassignment mutations are separate issues. Reminder
responses lack per-row capability flags, gift amounts and next-step descriptions;
the dossier supplies permitted context. No hosted tests, messages sent, backend
test suite, full Phase 3B governance gate or deployment were performed.
