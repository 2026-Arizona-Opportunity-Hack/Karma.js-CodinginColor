---
name: phase-review
description: Read-only adversarial review of a CIC Compass phase or lane (Review Phase N). Use when the human asks to review, audit or double-check a phase. Never edits code.
---

# Phase review (read-only)

You change no code and push nothing. You produce findings.

1. Read `docs/archive/ENGINEERING.md`, the phase in `docs/archive/PLAN.md`, the cited SRS IDs, and the phase report in `docs/archive/PHASE_LOG.md`.
2. Check out the phase's PR branches (or `main` after merge). Re-run every gate command yourself. Compare results with the report; any mismatch is a finding.
3. Try to break it. Minimum attempts for any phase that touches these areas:
   - **Authz:** call each new route as owner, other member, active super admin, dormant super admin, logged out, and with an API key. Try another member's donor id (IDOR). Try reassigning under `own_only`.
   - **Contact privacy:** fetch a donor you do not own; confirm email and phone are absent from the JSON, not just hidden in the UI.
   - **Import:** same file twice, shuffled rows, overlapping file, 6 MB file, renamed `.xlsx`, formula payload (`=HYPERLINK(...)`) in a name then export, non-USD row, bad date.
   - **Messaging:** send a draft directly by POST; edit after approval then send; approve as non-owner; double-click send.
   - **API:** no key, wrong key, revoked key, wrong scope; scan responses for donor names or emails.
   - **Governance:** any path from the app that creates, re-activates or deletes the super admin.
   - **Accessibility:** keyboard-only through the phase's screens; axe on each page; 390 px.
4. Output in `docs/archive/PHASE_LOG.md` under the phase report, section "Review": findings ranked by severity, each with reproduction steps and the requirement ID, plus a ready-to-paste `Fix Phase N: ...` prompt for the builder.
