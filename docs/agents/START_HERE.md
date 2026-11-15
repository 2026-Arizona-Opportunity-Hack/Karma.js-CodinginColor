# START HERE (CIC Compass kit v3, FastAPI)

## Install the kit into the team repo (5 minutes)
1. Copy `docs/` and `.claude/skills/` into the repo root (the repo's existing `.claude/settings.json` and `.claude/hooks/` stay untouched).
2. Append `AGENTS.project-section.md` to the end of the repo's `AGENTS.md`. Do not edit the organizers' text above it.
3. Commit on a branch, open the first PR (`Add project docs and agent rules`), merge.

## Accounts you create (human only; never paste keys into chat or commits)
- Render (web service, Starter) and Neon (Postgres, free). Keep `DATABASE_URL` in `.env` locally and in Render's env settings.
- Mail provider for live email later (optional; dry-run works without it).

## Run it
```
Run Phase 0          # single agent
Run Phase 1          # single agent
Run Phase 2 lane A   # three sessions at once, one per worktree
Run Phase 2 lane B
Run Phase 2 lane C
...
Review Phase 2       # optional separate session, read-only
Status
```
After each phase: read the report in `docs/PHASE_LOG.md`, follow its verification steps, merge PRs in the listed order, then run the next phase.

## Key times (Sun 15 Nov, MST)
Freeze 10:30 · draft video 10:45 · feedback hour 11:00 · record 12:00 · submit by 13:30 · deadline 14:00.

## Questions still open (defaults are already built in)
- Organizers: does an internal reminder email to board members count as a "reminder" that a human must send? (Default: human clicks "Send digest".)
- CIC: program list; fiscal or calendar year; whether contact details should be visible to all board members.
