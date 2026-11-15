# Issue #21 — Donor & gift entry QA

Scope: `frontend/` only, branch `lane-b/21-donor-gift-forms`. The requester explicitly waived the PR size limit and authorized a local commit. Publishing still requires approval under Engineering §7. `.agents/` is preserved and excluded.

## Readiness and contract review

Verified GitHub issue #21 (DON-7, DON-8, DED-6) and dependencies merged into `main`: #19 via PR #120, #20 via #124, #23 via #125, #22 via #132. Backend #73 is merged via #115/#116. Implementation began from `46d9e3940bca3af049cdd56f3e3604c7eafa7345`.

Inspected generated types, backend donor routes/schemas, donor write/gift services, repositories and authorization policy. Creation is open to authenticated members and assigns ownership by round-robin. Editing and gift creation require the owner or active super admin. Server permission hints gate actions; a 403 disables further writes, removes cached contact fields and preserves the open draft until dismissed.

## Design and focused polish

The entry desk extends the existing Stewardship Ledger rather than introducing new chrome. Names lead, because these are relationships with people and organizations. Numbered, ruled sections make identity, contact context and preferences easy to scan. Warm paper, forest actions and Georgia headings reuse the existing tokens in `src/index.css`. A gift receipt keeps the donor, exact amount and provenance visible before confirmation. Failure states keep the work intact and ask for a deliberate next action.

Evidence scan: [Attio](https://attio.com), [Stripe](https://stripe.com), [Linear](https://linear.app), and [Vandan Gohil’s nonprofit CRM case study](https://www.vandangohil.com/reports). Adapted identity hierarchy, financial clarity, restrained controls and explicit next actions; no copied assets or code.

Reused `QuickNoteSheet`, native form controls, shared buttons/states, generated contracts, authenticated CSRF client and TanStack Query keys. Extended the sheet with optional styling and eyebrow text. Extended `ApiError` to retain structured duplicate/validation responses.

| Workspace         | Primary task and states                                                                                                           | Keyboard and 390px behavior                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Create/edit donor | Grouped identity, contact and preferences; populated edit fields; validation, duplicate comparison, pending and confirmed success | Heading focus, labelled inputs, linked error summary, native focus trap/restoration; single column and persistent actions |
| Add gift          | Named donor receipt, decimal USD, business date, active programs when available; fixed manual/linked provenance                   | Same sheet behavior; scrollable fields and persistent actions; date stays a date-only string                              |

Inspected actual desktop, tablet and mobile captures. The focused polish pass moved Create donor into the directory topline, retained a roomy two-column desktop form, used a full-height single-column mobile desk and checked sticky actions. Captures wait for entrance motion to finish. Duplicate review and inline server validation remain readable without horizontal scrolling.

## Executed verification

- `npm run typecheck`, `npm run lint`, changed-source Prettier check and `npm run build`: passed.
- `npm run test:entry`: 5 passed (exact cents/range, structured duplicate handling, permission hints, uncertain-save handling and CSRF/error payload preservation).
- `npm run test:ledger`: 9 contrast tests passed. `npm run test:updates`: 3 tests passed.
- `npm run test:entry:browser`: passed at **390×844, 768×1024 and 1440×900** with headless local Chrome and synthetic API interception. Covers all donor kinds, create/edit, required and server validation, optional data, duplicate review/explicit separate creation, conflict without overwrite, gift cents/date/program, inactive program exclusion, 501 program fallback, CSRF, 400/401/403/404/409/422/500/501 and network failures, preserved drafts, uncertainty acknowledgement, synchronous double submissions, query refresh, restricted contact privacy, native discard confirmation, focus entry/trap/restoration, Escape and reduced motion. No gift-edit, gift-note or attribution mutation is invented.
- Existing `npm run test:detail` and `npm run test:contact`: both passed, including privacy, donor navigation, responsive layouts and contact/next-step workflows after the shared client/sheet changes.

The browser suite uses synthetic responses, not live backend writes. Chrome required elevated local execution. No FastAPI server was listening at `127.0.0.1:8000`; local Docker engine/context checks did not return. Real PostgreSQL mutation verification was therefore unavailable. No shared/hosted database was accessed. No manual screen-reader audit or actual 200% browser zoom run is claimed.

## Backend limitations

- `DonorUpdate` omits kind; edit displays it read-only. Optional contact/name/note fields can be cleared with null.
- No gift-edit endpoint exists. Gift history and entry explain this; there is no fake edit action.
- Gift notes are accepted by the schema but explicitly rejected by the service with 400. No editable gift-note field is exposed.
- `GET /programs` is still a 501 stub. The form explains unavailable choices and submits null for the server’s General default; no program IDs are guessed. Additional-program selection is covered with typed synthetic responses for when that endpoint becomes available.
- Manual gifts are fixed to source `manual`, attribution `linked`, zero fees and the donor named in the request URL. Source, donor, matching-gift status and imported attribution cannot be changed here. Anonymous Benevity gifts remain protected (D-131); existing import/review safeguards are reused.
- Creates have no idempotency key. Pending writes are locked synchronously and never automatically retried. Network/500 uncertainty requires checking saved records and explicit acknowledgement before retrying; cross-tab duplicates cannot be guaranteed away by the frontend.

## Captures and reproduction

Run Vite with `npm run dev -- --host 127.0.0.1`, then `npm run test:entry:browser` using Node 22+ and local Chrome (`CHROME_PATH` supported).

Representative screenshots: [desktop donor entry](1440-create.png), [desktop gift entry](1440-gift.png), [tablet gift](768-gift.png), [mobile donor entry](390-create.png), [mobile contact/preferences](390-create-context.png), [mobile gift fields](390-gift-fields.png), [duplicate review](390-duplicate.png), [server validation](390-server-validation.png), [unavailable programs](390-gift-default-program-fields.png). All records are synthetic.
