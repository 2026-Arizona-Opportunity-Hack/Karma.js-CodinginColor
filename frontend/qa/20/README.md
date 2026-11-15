# Donor detail & timeline — issue #20

Implemented on `lane-b/20-donor-detail`, based on merged PR #120. Changes stay in `frontend/`; generated contracts and backend code are unchanged.

The dossier reuses the directory masthead, status pills, error/empty/loading states, monetary/date formatting, shell, tokens and responsive patterns. The donor name leads, with a ruled giving summary and correspondence trail. Ownership, permitted contact information, notes and the next step sit alongside the story on desktop and precede it on mobile. Keyboard links jump to the timeline and gift history. Directory names open the detail route while preserving native recent-gift disclosure.

## Contracts and privacy

- `GET /api/app/donors/{id}` uses generated `DonorDetail`.
- `GET /api/app/donors/{id}/timeline` uses generated `TimelineOut`, enabled after successful detail authorization. Events are sorted newest first and display the returned kind, title, date, amount, detail and actor when available.
- Query keys include actor and donor IDs; requests use the existing API client and abort signals. Restricted email, phone and notes are stripped before entering the detail cache and never rendered when `contact_visible` is false. The screen shows `Contact via <owner>` instead.
- Email/call links require `contact_visible`, `can_act`, and no do-not-contact flag. These open the user's mail/phone application; the app does not send a message or claim to log contact.
- Gift history labels the detail endpoint's five most recent gifts; the timeline supplies earlier gift events. Employer matches retain their provenance and are distinguished from donor-contribution totals. The timeline labels its 500-event limit honestly.
- Entry forms and contact logging remain with #21/#23. No invented routes, synthetic runtime switch, dependencies, or writes were added.

## Verification

From `frontend/`, with Vite running at `http://127.0.0.1:5173`:

- `npm run test:detail`: passed. Covers all six event kinds, newest-first order, giving/ownership, missing contact values, independent visibility/action flags, do-not-contact, 0/1/20/205 events, slow detail and timeline loading, 401/403/404/500/501 recovery, independent timeline failure, keyboard focus/navigation, directory round trip, long names, reduced motion and responsive overflow checks.
- `npm run test:directory`: passed, including existing 205-record filtering/pagination, gift disclosure, keyboard and mobile navigation, errors and responsive checks.
- `npm run test:ledger`: nine contrast checks passed.
- `npm run test:updates`: three existing import-update tests passed.
- `npm run typecheck`, `npm run lint`, targeted `npx prettier --check`, and `npm run build`: passed. Production JavaScript: 334.70 kB (104.47 kB gzip).

The browser suites use local headless Chrome, Node 22+ and isolated synthetic API responses. Set `CHROME_PATH` if Chrome is installed elsewhere. Browser verification did not use a live backend. No claims of axe, screen-reader, or actual browser-zoom testing are made; 720×450 is a layout equivalent of 200% zoom on a 1440×900 display.

## Screenshots and polish

Inspected actual rendered [desktop](desktop.png), [mobile](mobile.png), and [restricted mobile](mobile-restricted.png) captures. Additional evidence: [tablet](tablet.png), [zoom-equivalent layout](zoom-equivalent.png), [dense history with long name](mobile-dense-long-name.png). Sizes are 1440×900, 768×1024, and 390×844; most captures include the full document.

One focused polish pass moved mobile ownership/contact context ahead of long histories, preserved a logical DOM order, refined the event-limit wording, and made loading announcements resource-specific. The final captures show no horizontal overflow or clipped names.

The cohesive implementation plus browser coverage exceeds the approximate 400-line repository preference. The human approved the size exception and proceeding with the PR after reviewing the implementation, checks, screenshots and commit. This approval satisfies ENGINEERING §7 and the Stewardship Ledger skill §0.3.
