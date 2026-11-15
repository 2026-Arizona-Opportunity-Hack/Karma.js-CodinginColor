# Log contact & next step — issue #23

Branch: `lane-b/23-contact-next-step`, based on `main` at `a187246`.
Verified on GitHub before implementation: #20 merged in PR #124; backend #74 merged in PR #80.
Only `frontend/` changes. No dependencies, generated contracts, backend, infrastructure, or #22 work.

## Design and behavior

The quick note sheet extends the existing Stewardship Ledger rather than introducing a new visual system. The donor's name anchors each entry so the board member always knows whose record is being updated. Five equally reachable contact choices make the common task immediate, while today's Phoenix date removes unnecessary input. Ruled sections, the existing Georgia headline, forest action color, paper surfaces, and restrained copper labels keep the sheet consistent with the directory and dossier. A bottom sheet on phones becomes a focused side workspace on larger screens. The next step remains beside the relationship story, with a single completion action and explicit replacement wording.

Reuse: existing shell, buttons, icons, theme tokens, dossier/timeline, date formatting, TanStack Query, generated API schemas, and CSRF-aware `api` wrapper. The established #19/#20 direction was retained without repeating visual research.

- **Contact:** open from the detail toolbar, choose Call/Text/Email/Meeting/Note, save. The browser test performs exactly three touch gestures at 390×844 without typing or scrolling. No contact type is assumed; notes are optional. Date defaults to today in America/Phoenix; future dates are blocked by native validation. Notes have the backend's 2,000-character limit.
- **Next step:** set a title (up to 200 characters) and due date; display the saved commitment; replace it explicitly; complete it through the backend, which logs an interaction. Title whitespace is rejected. Previous steps remain in history.
- **Feedback:** writes disable controls and prevent duplicate submissions; success appears only after a successful response. Validation, session, permission, conflict, unavailable-service and connection errors are announced. Failed entries remain intact. Close/Escape keeps the in-memory draft; a successful save clears it. Drafts do not survive page reloads and are never written to browser storage.
- **Accessibility:** native modal semantics with unique label/description IDs, heading entry focus (avoiding an automatic mobile keyboard), explicit Tab/Shift+Tab wrapping, radio arrow navigation, Escape handling and trigger focus restoration. If permission loss removes the trigger, focus returns to the workspace. During a pending write Escape does not dismiss the sheet. Existing reduced-motion rules disable sheet animation.
- **Privacy:** both `can_act` and `contact_visible` gate stewardship controls. A mutation 403 also clears `can_act` in the shared donor cache so both workflows stop offering writes. Draft contents are retained for the user to review. Existing restricted contact stripping remains in place. Do-not-contact records can log historical interactions/internal notes, with an explicit warning; nothing is sent.

## Contract integration

- `POST /api/app/donors/{id}/interactions`: generated `InteractionCreate` / `InteractionOut`.
- `PUT /api/app/donors/{id}/next-step`: generated `NextStepIn` / `NextStepOut`.
- `POST /api/app/next-steps/{id}/done`: generated `NextStepOut`.
- Successful writes invalidate donor detail, timeline, directory and reminder queries. 404/409 completion conflicts refresh detail/timeline before another attempt. Mutation retries are disabled to avoid replaying an uncertain write.
- **Existing read-contract limitation:** `DonorDetail` has a current next-step title/date but no ID or next-step read route. The actual backend timeline returns `kind: next_step`, `entity_id`, `title: Next step: <title>` and `detail: Due <date>`. Replacing a step cancels the old row and inserts a higher ID. Completion therefore uses the newest next-step entity only when its title/date exactly match the current donor summary and both reads are settled/successful. It never guesses an ID or completes an older matching title. If that entry is outside the timeline's 500-event window, missing, or unavailable, completion is disabled with an explanation; setting a replacement remains available. A dedicated current-step ID in the backend detail contract would remove this limitation, but generated contracts were not changed.

## Verification

From `frontend/`, run Vite at `http://127.0.0.1:5173` (`npm run dev -- --host 127.0.0.1`), then:

- `npm run test:contact`: passed. Real browser touch events verify the three-tap flow. Covers all five kinds, date/notes payloads, CSRF header, detail/timeline refresh, create/replace/reload/complete, missing-timeline recovery, 400/401/403/404/409/422/500/501 and interrupted-network states, preserved drafts, pending deduplication, keyboard focus and restoration, independent access flags, do-not-contact guidance, long names, responsive overflow and reduced motion.
- `npm run test:detail`: passed. Existing donor detail/timeline, privacy, errors, navigation, dense histories and responsive regression suite. Its regenerated #20 screenshots were restored to keep the change scoped.
- `npm run test:ledger`: passed, nine existing contrast checks.
- `npm run typecheck`, `npm run lint`, targeted `npx prettier --check`, `npm run build`: passed.

The browser suites use local headless Chrome and isolated synthetic responses. The new suite intercepts requests at the browser network boundary; the application still executes its actual fetch/CSRF client and TanStack Query lifecycle. No fixture switch is present in runtime code. These checks do not establish a live backend/database round trip or a manual screen-reader audit. The 720×450 screenshot verifies a layout equivalent to 200% zoom on 1440×900; it does not claim actual browser zoom testing.

## Screenshot review and focused polish

Inspected actual screenshots at 390×844, 768×1024, 1440×900 and 720×450. The focused pass corrected the next-step sheet's heading size, which inherited a smaller dossier heading style, and verified the resulting consistent serif hierarchy. The contact choices and save action are visible together at 390×844 for the standard three-tap path. Error/long-name states scroll within the sheet without horizontal overflow. Keyboard QA also exposed a focus-wrap edge and Chrome's noncancelable native cancel event during pending saves; explicit key handling now preserves focus and pending state.

- [Mobile contact](mobile-contact.png), [desktop contact](desktop-contact.png), [tablet contact](tablet-contact.png)
- [Mobile next step](mobile-next-step.png), [desktop next step](desktop-next-step.png)
- [Validation error](mobile-validation.png), [connection error](mobile-error.png), [saved state](mobile-success.png)
- [Long donor name](mobile-long-name.png), [restricted donor](mobile-restricted.png), [small-height / zoom-equivalent layout](zoom-contact.png)

This cohesive issue implementation plus browser coverage exceeds the repository's approximate 400-line PR preference. Size-exception approval is still needed before preparing a PR. ENGINEERING §7 also requires human approval before pushing or creating a PR. Neither action has been taken.
