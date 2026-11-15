# Issue 34 — reassignment and owner history

Branch: `lane-b/34-reassignment-history`. All records and screenshots are synthetic.

## Design

The handoff should feel deliberate and personal. The existing ledger typography keeps the donor at the center. A copper rule marks the departing steward, while a native owner selector makes the next action familiar. Explicit confirmation explains the change to access and reminders. The ownership trail records provenance in the same visual language as correspondence. Warm surfaces, forest actions, visible focus, and a scrolling mobile sheet reuse existing tokens and components.

Patterns consulted: [Attio records](https://attio.com/help/reference/managing-your-data/records), [Stripe dashboard](https://docs.stripe.com/dashboard/basics), [Linear properties](https://linear.app/docs/issue-properties-home), and [Sapling nonprofit CRM case study](https://www.vandangohil.com/reports). Patterns informed record context, restrained controls, explicit ownership, and actionable queues; no assets or code copied.

Anatomy: dashboard → View ownership → donor stewardship section → Reassign donor → active owner → optional reason → explicit confirmation. History remains available when reassignment is denied. Loading/error/retry use existing ledger components. Keyboard focus enters the sheet, stays inside, and returns on Escape; at 390px the sheet scrolls vertically.

## Verification

- `npm run typecheck`, `npm run lint`, `npm run build`: passed.
- Changed-file `npx prettier --check`: passed.
- `npm run test:dashboard`: passed, including read-only ownership navigation, 205-row dashboard, responsive layouts, reduced motion, and error recovery.
- `npm run test:ledger`: 9 contrast tests passed.
- Start `../backend/.venv/Scripts/python.exe tests/dashboard-local.py` and Vite. Run `$env:REASSIGN_QA='1'; node tests/dashboard-live.browser.mjs`: passed against isolated local Docker PostgreSQL/FastAPI. Verified persisted from/to/actor/method/reason, refreshed dashboard, confirmation, keyboard trap/Escape restoration, and preserved input across intercepted 401/403/409/422/500/501 failures.
- Additional real API checks on the isolated database: duplicate owner 409; active-super-admin/own-only denies another member's donor with 403 and redacts contacts; history remains readable; dormant/anyone permits handoff.
- Inspected settled screenshots at 390×844, 768×1024, 1440×900 and 720×450 (200% layout equivalent). Corrected capture timing to avoid sampling the sheet's opening animation. Mobile history wraps names and preserves the reason; no horizontal overflow in dialog checks.

## Boundaries

#33 is merged (PR #144, `7434bd5`); ownership backend is merged (`b17c7dd`). Issue #34 cites OWN-3/OWN-4. Uses existing GET members, GET owner-history and POST reassign contracts, server `can_reassign`, and existing cache keys. No generated/shared contract changes or new dependencies. Successful handoffs invalidate donor, timeline, history, directory, reminders/dashboard, and members.

No compare-and-swap/version parameter exists on reassign; the UI honors server responses without claiming stronger concurrency protection. Browser error statuses are controlled transport cases; the 403/409 policy checks above also exercised the actual backend. No hosted database or service was changed. Full automated assistive-technology certification and physical-device zoom were not performed. Evidence stays in frontend per lane scope. Implementation plus browser coverage exceeds the approximate 400-line PR target; obtain the team's size exception before preparing a PR. No push, PR, or #35 work.
