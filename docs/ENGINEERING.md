# CIC Compass: Engineering Rules for Agents

Read order at the start of every session: repo `AGENTS.md` (organizers' rules, they win on any conflict) → this file → `docs/SRS.md` → `docs/DATA_MODEL.md` → `docs/API.md` → `docs/PLAN.md` → `docs/DECISIONS.md` → `docs/PHASE_LOG.md`.

## 1. Commands

| Human says | You do |
|---|---|
| `Run Phase N` / `Run Phase N lane X` | Follow `.claude/skills/phase-runner/SKILL.md` for exactly that phase or lane. Then stop. |
| `Fix Phase N: <issue>` | Fix only that, inside the phase's scope; re-run its gate; update the report. |
| `Review Phase N` | Follow `.claude/skills/phase-review/SKILL.md`. Read-only. |
| `Status` | Summarize `docs/PHASE_LOG.md`: done, in progress, blocked, next. |

Never start a phase or lane you were not asked to run.

## 2. Hard rules

**Scope**
- Build only the current phase's issues. Improve-later items (SRS 3.2) and non-goals are forbidden until the human says so. Put ideas in the "Ideas" section of `PHASE_LOG.md`.
- Each P0 in its smallest correct form first.

**Lanes**
- In a lane, touch only that lane's paths (PLAN 1.3). Shared files change only in a `shared` PR merged first.

**PRs and issues** (organizers' rules)
- One issue per task; branch `lane-x/<issue#>-slug` or `phase-n/<issue#>-slug`; one PR per issue, under ~400 changed lines; title imperative under 72 chars; body under 500 words in the template order; `Closes #N`; open with `gh pr create`.
- Never commit to `main`, never force-push a shared branch, never merge your own PR. The human merges.

**Data and privacy**
- Synthetic data only. Never create, request or paste real donor or payment data anywhere.
- Never claim a fixture is a real platform format. Use `IMPORT_FORMATS.md` and mark assumed formats.
- The public API and MCP return aggregates only. A test enforces it.

**Messages**
- The system drafts; a human approves and sends every donor message. No scheduled or automatic sends to donors. `MESSAGING_MODE=dry_run` unless the human configures `live`.

**Security**
- Every DB access goes through a repository function that takes the `Actor` and calls `policy.can()`. No queries in route handlers.
- Hiding a button is not authorization. Every new route gets policy tests (allowed and denied) in the same PR.
- Secrets only in env; update `.env.example` with placeholders. Do not work around the repo's guard hook.
- Validate all input with Pydantic; uploads checked for size and type; exports neutralize formulas.
- No hard deletes of users, donors, gifts or messages. Super admin can never be removed or granted from the app.

**Dependencies**
- Use the approved list below. Ask before adding anything else. Pin exact versions. No packages published in the last 14 days.

**Honesty**
- Never say a test passes unless you ran it in this session; paste the command and a short result.
- Unfinished or hacky work goes under "Known gaps" in the report.

## 3. Stack and approved dependencies

Backend: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `argon2-cffi`, `openpyxl`, `python-multipart`, `httpx`, `python-dateutil`, `phonenumbers`, `mcp` (MCP server only). Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `faker`.

Frontend: `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `tailwindcss`, `@radix-ui/*` (as needed), `clsx`, `lucide-react`, `openapi-typescript`. Dev: `vite`, `typescript`, `eslint`, `prettier`, `@playwright/test`, `@axe-core/playwright`, `@lhci/cli`.

## 4. Layout

```
backend/
  app/
    main.py               # app factory, routers, static SPA mount
    settings.py           # env via pydantic-settings
    cli.py                # setup, superadmin, seed-demo, reset-demo
    clock.py              # injectable clock (America/Phoenix)
    db/ session.py, models/
    authz/ actor.py, policy.py
    repos/                # ONLY place with SQL; every function takes Actor
    services/ ingest/ dedupe/ ownership/ reminders/ messaging/ reports/ apikeys/ audit/
    routes/ app_*.py      # /api/app/*  (session + CSRF)
            v1/           # /api/v1/*   (API key, aggregates)
    schemas/              # Pydantic request/response models (the contract)
  alembic/
  tests/ unit/ integration/ authz/
frontend/
  src/ api/ (types.ts generated, client.ts) pages/ components/ hooks/ lib/
  e2e/
mcp_server/
fixtures/ generate.py, *.csv, *.xlsx, manifest.json
docs/
```

## 5. Code patterns

- Route handlers are thin: parse with a schema, build `Actor`, call a service, return a schema.
- Services hold rules; repos hold SQL; both are unit-testable with the injected clock.
- Transactions: one per request for writes; import commit, round-robin and merges in a single explicit transaction.
- Money as `int` cents everywhere; format only in the UI.
- Errors: raise typed exceptions (`NotFound`, `Forbidden`, `Conflict`, `Invalid`) mapped centrally to 404/403/409/400.
- Frontend: TanStack Query per resource; forms with native inputs and labels; every interactive element reachable by keyboard; visible focus; no colour-only status.

## 6. Definition of done for a PR

- Issue linked; scope matches the issue; under ~400 lines or split.
- `ruff`, `mypy` (backend), `tsc`, `eslint` clean; tests added and passing; policy tests for new routes.
- `.env.example`, docs and `PHASE_LOG.md` updated if behaviour or setup changed.
- PR body: what, why, how to test (exact steps), screenshots for UI.
