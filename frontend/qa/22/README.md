# Import Upload & Review - issue #22

Branch: `lane-b/22-import-review`; base: current `origin/main` at `77b8965`.
All changes are in `frontend/`. No dependency additions, generated contract edits, backend changes or #21 work.
The requester explicitly approved ignoring the approximate PR size limit for this cohesive issue. Push and PR creation still require approval under ENGINEERING section 7.

## Dependency and contract checks

Verified GitHub before implementation: #19 / PR #120, #20 / PR #124 and #23 / PR #125 are merged into main. PR #112 is also merged; its import page and default-unchecked spreadsheet approvals are extended here.
Issue #22 cites ING-4, ING-5 and DED-4. Read the import formats, dedupe and attribution rules, generated API types, OpenAPI schemas, import routes, preview cache, commit service and review/attribution implementations.

The actual sequence is preview -> confirmation -> commit -> identity review. Preview stores no donors or gifts. Review candidates become available only after commit; the preview contract has no candidate identities or editable raw cells. Commit is atomic and revalidates against current database state. The preview cache lasts up to 20 minutes and can be evicted or lost on restart. A commit failure requires a status lookup before another attempt. A confirmed committed status recovers a lost success response without another POST. Conflict or expired previews require reupload and fresh approvals.

## Design

This workspace extends the existing Ledger tokens, Georgia headings, ruled surfaces, shared page masthead, query architecture, API client and accessible confirmation sheet. Source rows tell the provenance story; donor identities and gift records remain distinct. The reconciliation table presents physical rows, generated gifts, donation cents and employer-match cents as separate columns. On phones and tablets it becomes a labeled vertical audit ledger. The comparison desk prioritizes name, email, phone and organization, while additional normalized source fields remain available in a disclosure. Candidate names, identifiers, owners and match reasons appear alongside incoming identity evidence; donor dossier links expose only what the existing backend permits. Confirmation explains what will be saved before any write, and server-confirmed success leaves pending identity work visible.

Focused reference scan: [Attio imports](https://attio.com/help/reference/imports-exports), [HubSpot import formatting](https://knowledge.hubspot.com/import-and-export/set-up-your-import-file), [Linear import guide](https://linear.app/docs/import-issues), and [Vandan Gohil's nonprofit CRM case study](https://www.vandangohil.com/reports). Patterns informed source guidance, explicit stages and action-oriented comparisons; no screens, assets or code were copied.

Screen anatomy: upload answers which source/file to use; preview answers what is valid and what will change; confirmation explains the transaction; review answers whether incoming and existing identities belong together. Native labeled controls provide the keyboard path. Loading, retry, empty, validation, permission, conflict and uncertain-outcome states retain the relevant working values. Invalid reasons remain verbatim. Familiar one-based file rows are displayed alongside the original zero-based backend references, including headers. No source values are rewritten in the browser.

## Verification completed

- `npm run typecheck`: passed.
- `npm run lint`: passed.
- Changed source, tests and config: `prettier --check`: passed.
- `npm run build`: passed.
- `npm run test:import`: 4 passed, including precise Benevity opt-out rules, file boundaries, actual multipart/CSRF client behavior, error status and reason preservation, and no automatic commit retries.
- `npm run test:updates`: 3 passed: unchecked defaults, exact approved fields, hidden old contact values.
- `npm run test:ledger`: 9 existing token contrast tests passed.
- `node tests/import.browser.mjs`: passed with isolated synthetic network responses through the actual application client. Covers 390x844, 768x1024 and 1440x900, verbatim invalid reasons, source-row/gift-count differences, spreadsheet zero-gift rows and approvals, repeated-click prevention, explicit confirmation, all three identity decisions, upload and commit status errors, permission failures, expired previews, server-blocked commit, conflict reload, lost-success-response recovery, CSRF, Benevity protection, and successful generic anonymous-gift attachment. Also covers 0/1/20/200 review records, long identities, reduced motion and a 720x450 layout equivalent to 200% zoom. Native dialogs receive focus and close with Escape; no horizontal page overflow was detected.
- `node tests/import-live.browser.mjs`: passed at all three target sizes, with **no API interception**. Used local FastAPI at 127.0.0.1:8000 and isolated local PostgreSQL database `cic_22_browser`. Completed donor-only CSV import, a Zeffy file with a bad-date row and a possible duplicate, explicit commit, an existing-donor identity decision, and a Benevity file with 2 source rows generating 3 gifts, including protected anonymous gifts.
- Backend regression command, run with `DATABASE_URL` and `TEST_DATABASE_URL` explicitly pointing to isolated local `cic_22_tests`:

```powershell
./.venv/Scripts/python.exe -m pytest -q tests/unit/test_import_summary.py tests/unit/test_import_preview.py tests/unit/test_import_row_keys.py tests/integration/test_import_preview.py tests/integration/test_import_commit.py tests/integration/test_identity_reviews.py tests/integration/test_gift_attribution.py
```

65 passed. Existing Starlette/httpx deprecation and a nonfatal pytest-cache write warning were emitted. No shared or hosted database was used.

## Screenshot review and polish

Inspected actual rendered screenshots at the three target viewports. The focused polish pass moved core identity fields ahead of secondary normalized fields, shortened the mobile explanation behind a disclosure, and replaced the crowded tablet table with labeled stacked classifications. Long synthetic identities wrap without clipping. Candidate and decision controls remain reachable vertically on mobile.

Representative captures (all synthetic):

- [Desktop reconciliation](1440-preview.png)
- [Desktop live identity comparison](1440-live-comparison.png)
- [Desktop live server-confirmed import](1440-live-success.png)
- [Mobile live invalid-row preview](390-live-preview.png)
- [Mobile live incoming identity](390-live-comparison.png)
- [Mobile live candidates and decision](390-live-candidates.png)
- [Mobile confirmation](390-confirm.png)
- [Mobile attribution protection](390-attribution.png)
- [Tablet live reconciliation](768-live-preview.png)
- [Tablet live comparison](768-live-comparison.png)

## Reproduction and limits

Start Vite with `npm run dev -- --host 127.0.0.1`, then `npm run test:import:browser`. Requires Node 22+ and local Chrome; set `CHROME_PATH` if it is not in the standard Windows location. The previous `import-updates.browser.mjs` entry point delegates to this complete suite so its field-approval coverage stays current.

The live runner additionally requires an **isolated local** backend/database and a synthetic member. Keep local test credentials in ignored `.test-build/22-session.json` as `{"email":"<synthetic email>","password":"<local password>"}`; do not commit it. The runner makes real imports and resolves unfinished synthetic reviews in that dedicated database. It must not be pointed at a shared database. Screenshots are generated into `qa/22`; only representative captures are retained in the commit.

API limits are represented honestly: raw source cells and candidate contacts are not returned; per-row exclusion and pre-commit duplicate decisions are unavailable. Correct the original file and preview again to exclude a valid row. Marking a review anonymous retains its gifts, rather than excluding the row. Unattributed gifts include pending-review gifts and are limited by the backend to 500; pending gifts direct users back to identity review. Only source=benevity AND attribution=anonymous suppresses donor attachment. Server 409 responses remain authoritative.

Fetch does not expose upload byte progress, so the upload state is indeterminate with no invented percentage. The backend provides no partial transaction-success response; invalid/duplicate rows are explained as skipped and final counts come from the saved batch. No messages are sent. No manual screen-reader audit, actual browser zoom test, production deployment or hosted-data validation is claimed.
