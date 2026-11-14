---
name: phase-runner
description: Runs exactly one phase or lane of the CIC Compass plan (Run Phase N, Run Phase N lane X, Fix Phase N). Use whenever the human asks to run, continue or fix a phase.
---

# Phase runner

1. **Load context.** Read repo `AGENTS.md`, `docs/ENGINEERING.md`, then the phase section in `docs/PLAN.md`, the SRS requirement IDs it cites, `docs/DECISIONS.md`, and the latest `docs/PHASE_LOG.md`. Confirm with `git status` that you are on a clean worktree based on current `main`.
2. **Plan briefly.** List the phase's issues in merge order. For each: files you will touch (must be inside your lane, or a `shared` PR), tests you will add, the SRS IDs it satisfies. If an issue would exceed ~400 changed lines, split it now and create the extra issue with `gh issue create`.
3. **Per issue:**
   - Branch `lane-x/<issue#>-slug` (or `phase-n/...`) from `main` (or from the previous branch in the same lane if it is not merged yet; say so in the PR).
   - Write tests first for rules (row_key, round-robin, policy, state machine, reminders), then code.
   - Run `ruff`, `mypy`, `pytest` (backend) and `tsc`, `eslint`, build (frontend) as relevant. Fix until green.
   - Commit with messages that explain why. Push and `gh pr create` using the template: what changed, why, how to test (exact commands or clicks), screenshots for UI, `Closes #N`. Keep the body under 500 words.
4. **Gate.** Run every gate item from the phase. Record evidence (command and short output, or test names). Do not tick an item without evidence.
5. **Report.** Append the report template in `docs/PHASE_LOG.md` (open a small docs PR or include in the last PR of the phase), update the status board to `ready-for-review`.
6. **Stop.** Final message: PRs in merge order, gate pass/fail per item, exact verification steps, known gaps, questions. Do not start the next phase.

If blocked: choose the safest documented default (DECISIONS, SRS assumptions), note it under "Decisions made", ask under "Questions for the human", and continue. Stop only if a gate item is impossible without an answer.

If a phase runs more than 45 minutes over its gate target, apply its cut list in order and record what was cut.
