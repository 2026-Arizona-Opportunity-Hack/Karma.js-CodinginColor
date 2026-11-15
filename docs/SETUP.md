# Setup

Run CIC Compass on your own machine, load the synthetic test data, run the checks, and deploy.

**Contents:** [Prerequisites](#prerequisites) · [Install and run](#install-and-run) · [Environment variables](#environment-variables) · [Load test data](#load-test-data) · [Verify it works](#verify-it-works) · [Tests and checks](#tests-and-checks) · [Optional features](#optional-features) · [Deployment](#deployment) · [Troubleshooting](#troubleshooting)

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| [Git](https://git-scm.com) | any recent | clone the repository |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | any recent | local PostgreSQL 16 (`docker-compose.yml`) |
| [uv](https://docs.astral.sh/uv/) | 0.13 or newer | installs Python 3.12 and the pinned backend dependencies (`backend/uv.lock`) |
| [Node.js](https://nodejs.org) | 22 or newer | the web app (Vite 8) |

No accounts or API keys are needed to run locally. Email stays in dry-run mode and the assistant stays off.

## Install and run

1. Clone and configure:
   ```bash
   git clone https://github.com/2026-Arizona-Opportunity-Hack/Karma.js-CodinginColor.git
   cd Karma.js-CodinginColor
   cp .env.example .env
   ```
   The defaults in `.env` match the local database. `.env` is git-ignored; never commit it.
2. Start PostgreSQL:
   ```bash
   docker compose up -d db
   ```
3. Install the backend and create the tables:
   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   ```
4. Create accounts. Either load the demo (see [Load test data](#load-test-data)), or add your own board members:
   ```bash
   uv run python -m app.cli setup
   ```
   It asks for each member's email and display name, then prints each initial password **once**. To script it, put `{"members": [{"email": "...", "display_name": "..."}], "super_admin": null}` in a git-ignored `members.local.json` at the repo root and run `uv run python -m app.cli setup --file ../members.local.json`.
5. Start the API:
   ```bash
   uv run uvicorn app.main:app --reload     # http://localhost:8000, API docs at /api/docs
   ```
6. In a second terminal, start the web app (it proxies `/api` to port 8000):
   ```bash
   cd frontend
   npm ci
   npm run dev                              # http://localhost:5173
   ```

## Environment variables

Settings are read from `.env` in `backend/` or the repo root (`backend/app/settings.py`). Real environment variables override `.env`.

| Name | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | `postgresql+psycopg://cic:cic@localhost:5432/cic` | PostgreSQL connection. In production, the Neon connection string (`postgres://` and `postgresql://` are both accepted). Secret. |
| `APP_ENV` | no | `dev` | `dev`, `test` or `prod` |
| `COOKIE_SECURE` | no | `true` | Secure session cookies. Browsers accept them on `http://localhost`; set `false` only for plain http on another host. |
| `MESSAGING_MODE` | no | `dry_run` | `dry_run` records sends and delivers nothing; `live` sends email through Resend. |
| `RESEND_API_KEY` | only for `live` | empty | [Resend](https://resend.com) API key. Secret. |
| `MAIL_FROM` | only for `live` | empty | Sender, for example `CIC Compass <compass@your-domain.org>` |
| `DEMO_MODE` | no | `false` | Allows the `seed-demo` and `reset-demo` commands. Never in real use. |
| `AI_GATEWAY_URL`, `AI_GATEWAY_KEY`, `AI_GATEWAY_MODEL` | only for the assistant | empty | Chat-completions endpoint for the optional assistant. The key is secret. |
| `SESSION_IDLE_HOURS`, `SESSION_ABSOLUTE_DAYS` | no | `12`, `7` | Session lifetime |
| `TIMEZONE` | no | `America/Phoenix` | Business dates and reminder due dates |
| `STATIC_DIR` | no | `../frontend/dist` | Built web app served by FastAPI (set by the Docker image) |
| `TEST_DATABASE_URL` | tests only | `postgresql+psycopg://cic:cic@localhost:5432/cic_test` | The test database. The suite truncates every table, so never point this at a shared database. |

## Load test data

All test data is synthetic (see [DATA.md](DATA.md)). With the backend installed and migrated:

```bash
cd backend
DEMO_MODE=true uv run python -m app.cli seed-demo
```

This creates three demo board members (`diana@demo.cic.test`, `marcus@demo.cic.test`, `priya@demo.cic.test`), prints their passwords once, and imports the four files in `fixtures/` through the real importer. Expected result: 225 donors, 531 gifts, 19 items waiting in Review.

To start over: `DEMO_MODE=true uv run python -m app.cli reset-demo` (wipes **every table**, then seeds again).

To try the import screen yourself instead, run only `setup`, sign in, open **Import** and upload the files from `fixtures/` in this order: `synthetic_cic_spreadsheet.xlsx`, `synthetic_zeffy_like.csv`, `synthetic_benevity_like.csv`, `synthetic_generic_azgives_like.csv`.

## Verify it works

1. `http://localhost:8000/healthz` returns `{"status":"ok"}`.
2. `http://localhost:5173` shows the sign-in page. Sign in with a demo account.
3. **Dashboard** lists reminders; **Relationships** lists donors; **Review** has the 19 review items; **Reports** shows the giving summary and retention.
4. Sign in as a second member in a private window: you see the first member's donors' gift history but not their email, phone or notes.

## Tests and checks

```bash
# backend: lint, format, types, tests (needs the Docker database running)
cd backend
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest

# web app: types, lint, format, production build
cd frontend
npm run typecheck && npm run lint && npx prettier --check src && npm run build

# MCP server
cd mcp_server
uv sync && uv run pytest
```

`pytest` creates the `cic_test` database on first run. The importer's acceptance test (`tests/integration/test_import_commit.py -k finished_importer`) checks every number in `fixtures/manifest.json`. GitHub Actions runs all of the above, plus a Docker build and a gitleaks secret scan, on every push and pull request (`.github/workflows/ci.yml`).

The frontend's `npm run test:*` scripts are browser checks against a running dev server with mocked API responses; they need a local Chrome (`CHROME_PATH` to override) and save screenshots to `frontend/qa/` (git-ignored).

## Optional features

- **Live email.** Set `MESSAGING_MODE=live`, `RESEND_API_KEY` and `MAIL_FROM` (a domain verified in Resend). Until then every send is recorded as a dry run and the app says so.
- **Assistant.** Set the three `AI_GATEWAY_*` variables, then turn it on (there is no settings screen for this yet):
  ```bash
  docker compose exec db psql -U cic -d cic -c "INSERT INTO app_settings (key, value) VALUES ('assistant_enabled', 'true'::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;"
  ```
- **Read API and MCP server.** Create a key with `uv run python -m app.cli apikey create --name Dashboard --email <member email>`, then follow [API_GUIDE.md](API_GUIDE.md) and [mcp_server/README.md](../mcp_server/README.md).

## Deployment

The live demo runs as one Docker service on Render (`render.yaml`, free plan) with a Neon PostgreSQL database. Pushing to `main` redeploys automatically; the container runs `alembic upgrade head` before starting. Run a **single** process: import previews live in memory between Preview and Commit. Step-by-step first deploy, environment variables, the break-glass super admin command and key rotation: [DEPLOY.md](DEPLOY.md). Costs: [COSTS.md](COSTS.md).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `connection refused` on port 5432 | The database container is not running | `docker compose up -d db`, then `docker compose ps` |
| Sign-in works but you are signed straight out | Secure cookie over plain http on a host other than `localhost` | Use `http://localhost:5173`, or set `COOKIE_SECURE=false` locally |
| `Refusing: set DEMO_MODE=true` | Demo commands are disabled by default | Prefix the command with `DEMO_MODE=true` |
| "The synthetic fixtures folder was not found" | `seed-demo` run outside the repo checkout | Run it from `backend/` inside the cloned repo |
| Commit after preview fails with an expired preview | Previews last 20 minutes in one process; a restart clears them | Upload the file again |
| "Too many attempts" at sign-in | Login rate limit after repeated wrong passwords | Wait 15 minutes |
| A screen says "Not available yet" | That endpoint is still a stub (programs, program map, settings, donor merge) | See [ROADMAP.md](ROADMAP.md) |
| The live app takes a minute to load | Render's free plan sleeps after 15 minutes idle | Open it a minute before a demo, or use the Starter plan |
| Tests wiped your data | `TEST_DATABASE_URL` pointed at your main database | Keep tests on `cic_test`; never on a shared database |
