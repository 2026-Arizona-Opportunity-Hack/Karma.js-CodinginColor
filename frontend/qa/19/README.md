# Donor directory verification — issue #19

Stewardship Ledger: warm paper surfaces, Georgia headings, forest actions, ruled relationship rows, tabular USD amounts and adaptive mobile dossiers. Shared components cover the masthead, status labels, loading, errors and empty states. Existing authentication, import routes and generated contracts are preserved.

The user approved cohesive issue PRs exceeding the approximate 400-line preference. This PR closes only #19. The subsequent detail, contact, import/review and entry-form issues remain separate.

## Checks

From `frontend/`:

- `npm run typecheck` — passed.
- `npm run lint` — passed.
- `npm run build` — passed; 326.51 kB JavaScript, 102.75 kB gzip.
- `npm run test:updates` — three existing import-update tests passed.
- `npm run test:ledger` — nine token-contrast tests passed. Normal-text pairs: 5.36–14.67:1; control border: 3.09:1.
- `npm run test:directory` — passed against Vite with isolated synthetic API responses. Requires Node 22+, local Chrome (or `CHROME_PATH`) and Vite running on 127.0.0.1:5173. No dependencies added.
- `npx prettier --check src` — fails on six **untouched** files: `components/DonorUpdateReview.tsx`, `hooks/useAuth.ts`, `lib/donorUpdates.ts`, `pages/ImportPage.tsx`, `pages/LoginPage.tsx`, `pages/PlaceholderPage.tsx`. All changed source files pass a targeted Prettier check. Three pre-existing failures were resolved while modifying the shell/styles/routes; additional untouched failures came from the import work now on main.
- Existing backend `test_donor_read_api.py`: nine tests passed, using only isolated local PostgreSQL database `cic_lane_b_19_test`. One existing Starlette/httpx deprecation warning. No backend files changed.

## Browser evidence

Synthetic browser responses exercise 0, 1, 20 and 205 records, My/All, server query parameters, pagination and filter reset, native keyboard search/disclosure, mobile navigation, Escape focus restoration, long names, slow loading, and 401/403/409/422/500/501 recovery. Search terms remain out of browser URLs. Production code has no synthetic-data switch or mock fetch implementation.

The optional `DIRECTORY_LIVE_URL` mode uses a **localhost-only** FastAPI server with synthetic seed data and caller-provided `DIRECTORY_QA_EMAIL` / `DIRECTORY_QA_PASSWORD`. It performs real UI login, My/All browsing, search and gift expansion and checks that the real API masks another owner's email/phone and denies donor actions. This pass succeeded against the isolated local database. It does not intercept API requests.

Screenshots inspected at 1440×900, 768×1024 and 390×844:

- [Desktop](desktop.png), [expanded gifts](desktop-gifts.png)
- [Mobile](mobile.png), [long-name mobile](mobile-long-name.png)
- [Tablet](tablet.png)
- [Real local API with synthetic seed data](live-local.png)

No horizontal overflow at tested widths, including the 720×450 CSS viewport equivalent of 200% zoom on 1440×900. Reduced-motion styles disable transitions. Native summary controls, labeled inputs, visible focus and a skip link are present. Lighthouse/axe and screen-reader testing have not been run; viewport equivalence is not a claim of browser zoom testing.

## Known limits

- `/members` and `/programs` return 501 on current main. Owner choices fall back to the current user and owners on the current page, with an explicit explanation. Program filtering is disabled until choices are available. Both endpoints are retriable; populated contracts are covered by synthetic browser QA.
- Thank-you/update due statuses are not implemented by the current backend reminder service. Those filter choices are explicitly disabled. Returned status chips are rendered as supplied, without invented reminders.
- Donor detail navigation and mutation actions belong to the subsequent issues. This directory expands the last five linked gifts provided by the list API.
- #73's backend PRs #115 and #116 are merged. Write behavior and generated contracts will be verified again at the start of #21.
- No pushes, PR creation, deployment, Render/Neon access, generated-contract edits or changes outside `frontend/` were performed.
