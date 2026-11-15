# Issue 35 — Members & governance

## Design blueprint

The board is a circle of stewards, and settings should make that shared responsibility legible. Names lead the directory, followed by access and the relationships each person carries. The existing parchment, forest, copper, Georgia headings, and ruled surfaces keep this workspace part of the Stewardship Ledger. A governance charter is the signature module: it explains who can act before offering controls. Consequential changes use the existing accessible sheet, with plain-language consequences and deliberate confirmation. Mobile rows become stacked entries, preserving every action without horizontal scrolling.

Reuse: Layout, PageMasthead, EmptyState, ErrorState, LoadingLedger, QuickNoteSheet, native form controls, api/CSRF client, generated contracts, and actor-scoped TanStack Query keys. No new dependencies or shared component rebuild.

Anatomy: Settings masthead → governance charter and scope → searchable member ledger → invitation or deactivation sheet. Governance is readable to all members; only the active super admin sees scope/flatten controls. Flat-mode members can invite and deactivate eligible peers. At 390px all sections stack; dialogs scroll vertically. Native controls, dialog focus trap/restoration, Escape, status/error announcements, and explicit checkboxes support the keyboard path. Loading, fetch failure/retry, no members, no matches, restricted access, and confirmed server success each have distinct states.

Research: [Stripe team management](https://docs.stripe.com/get-started/account/teams), [Linear members and roles](https://linear.app/docs/members-roles), [Attio workspace](https://attio.com), [Sapling nonprofit workflow case study](https://www.vandangohil.com/reports). Patterns: identifiable members, visible suspended status, least-privilege actions, and a next step attached to consequences. No assets or code copied.

## Contract and scope

GitHub #35: “Invite, deactivate, scope, flatten button for super admin.” #34 merged via #146 (`1c78e51`); required Phase 3A member and governance APIs merged via #121 (`20873ce`) and #122 (`069198b`). All are ancestors of the starting HEAD, which matches fetched main.

AUTH-4/7, GOV-1–7, OWN-5. The invitation API creates a one-time 72-hour link and sends no email. Its `/invite/:token` destination needs a public acceptance form; acceptance creates the account without logging it in. Member records retain donor assignments after deactivation. No pending-invite list, resend/revoke, member edit/reactivation, or app-based super-admin grant exists. The super-admin holder is protected even when dormant; self-deactivation is forbidden. Flat scope is fixed to anyone. Bulk donor move is the Phase 3 cut-list item, outside this issue.

The user explicitly waived the approximate PR size target and authorized a local commit. Work remains frontend-only; push and PR require separate approval under Engineering §7. Untracked `.agents/` is preserved.

## QA results

- `npm run typecheck`, `npm run lint`, `npm run build`: passed. Vite emitted informational plugin timing output; the production build completed successfully.
- `npm run test:ledger`: 9 contrast tests passed.
- `npm run test:members`: passed. Covers active-admin, flat-member, dormant-holder, and restricted-member permissions; native required-email validation; invitation creation and acceptance; preserved inputs for 401/403/409/422/500/501; deactivation, scope, and flatten errors; renewed confirmation after failed destructive writes; successful query refresh; dialog heading focus, forward/reverse Tab wrap, Escape and restoration; 0/3/205 records, search, long names, loading, empty, and read retry. Transport fixtures are isolated synthetic responses, not a production fallback.
- `npm run test:members:live`: passed against local FastAPI and a fresh Docker PostgreSQL database. Verified actual 403 restrictions, duplicate-invite 409, one-time acceptance and consumed-link 400, separate sign-in after joining, persisted scope, member deactivation retaining two donors, two Needs reassignment entries, duplicate-deactivate 409, immediate revocation of an independently authenticated session, blocked deactivated login, flatten to dormant/anyone, refreshed auth, protected dormant holder, and invitation access for flat-mode peers. See `live-results.json`.
- Screenshot polish: inspected 390×844, 768×1024, and 1440×900, plus a 720×450 layout equivalent to 200% desktop zoom. Corrected the search control to reuse the established bordered style; stacked tablet member rows when the navigation rail leaves limited space; captured fixed dialogs at viewport size. No horizontal overflow in viewport assertions. Dense-list screenshots show the viewport rather than a 200-row image. Live invitation links are redacted in screenshot captures.
- The live test exposed the dev proxy's backend-origin invitation URL. The UI now keeps the server-issued path on the current frontend origin; the live test explicitly verifies the copied link's origin.

Reproduce: start `npm run dev -- --host 127.0.0.1`; run `npm run test:members`. For real backend flows, start `../backend/.venv/Scripts/python.exe tests/members-local.py` with local Docker PostgreSQL available on 127.0.0.1:5432, then run `npm run test:members:live`. Each fixture launch creates a unique `cic_35_*` database, never reads hosted connection URLs, and keeps its credentials in ignored `.test-build/35-session.json`. Restart the fixture before repeating the destructive live suite. Chrome defaults to its standard Windows path; override `CHROME_PATH` if needed. JSON evidence records paths/status checks without request bodies or invitation tokens.

## Boundaries and remaining limitations

Backend capabilities intentionally constrain the UI: no invitation email delivery, pending-invite listing, resend/revoke, member editing/reactivation, or in-app super-admin creation/reactivation/transfer. Shared settings beyond governance belong to later issues. No backend, generated contract, root documentation, hosting, or shared-database changes. All records are synthetic. No physical-device or assistive-technology certification; the 200% check is a viewport layout equivalent. No push or PR has been performed.
