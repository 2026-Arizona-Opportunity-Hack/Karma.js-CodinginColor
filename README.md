# CIC Compass

A donor stewardship app for [Coding in Color](https://www.ohack.dev/nonprofit/YIXYdYCoxIZC08uQ5DL3) (CIC). It keeps donors and funders in one place so nobody has to hunt through exports from several giving platforms to see who gave, when, and who last got in touch.

Built for CIC's [Donor & Funder Relationship Platform](https://www.ohack.dev/project/e26932c0df1b11f189a8dead68f07eb5) problem statement at the ASU Fall Hackathon 2026 by team Karma.js. Open source under the MIT license.

**Current version:** 0.1.0 (foundation). See the [changelog](docs/CHANGELOG.md).

## What it does

**Available now**
- Individual board-member accounts with secure login, sessions and CSRF protection.
- A flat hierarchy by default, with an optional single super admin managed only from the command line.
- An audit log of logins and governance changes.
- A web app shell with navigation for Dashboard, Donors, Import, Review, Messages, Reports and Settings.

**Designed scope** (full requirements in [docs/SRS.md](docs/SRS.md))
- Import gifts from CSV/XLSX exports (Zeffy, Benevity, a generic template, and CIC's donor spreadsheet) into one de-duplicated donor ledger.
- Share donors across board members round-robin, with manual reassignment and a visible ownership history.
- Donor timeline, follow-up reminders and a quarterly touch for every donor.
- Thank-you and update messages drafted by the system; a person approves and sends every one.
- Retention view, one-click funder export, and a key-authenticated, aggregate-only read API with a read-only MCP server.

## Design principles

- **A human sends every donor message.** The app drafts; board members approve and send. Email runs in dry-run mode unless explicitly configured for live sending.
- **Employee giving excludes employer matches.** Match gifts remain org revenue, while donor totals, lifetime giving, retention and pre-filled message amounts use only the employee's donation ([D-127](docs/DECISIONS.md)).
- **Privacy by default.** Every board member sees gift history; contact details are visible only to a donor's owner. The public API returns aggregates only, never donor details.
- **No secrets in the repository.** Configuration comes from environment variables; `.env` is git-ignored.
- **Synthetic data only** in this repository.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Argon2id |
| Frontend | React, Vite, TypeScript, Tailwind CSS, TanStack Query |
| Database | PostgreSQL 16 (Docker locally, [Neon](https://neon.com) hosted) |
| Hosting | One Docker image on [Render](https://render.com) serving the API and the web app |
| Email | [Resend](https://resend.com) (optional, off by default) |
| CI | GitHub Actions: ruff, mypy, pytest, TypeScript, eslint, build, gitleaks |

## Run it locally

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [uv](https://docs.astral.sh/uv/) (it installs Python 3.12), plus Node 22+.

```bash
git clone https://github.com/2026-Arizona-Opportunity-Hack/Karma.js-CodinginColor.git
cd Karma.js-CodinginColor
cp .env.example .env              # fill in your own values; never commit .env
docker compose up -d db           # local Postgres on :5432

cd backend
uv sync                           # install pinned dependencies
uv run alembic upgrade head       # create tables
uv run python -m app.cli setup    # add board members; prints each initial password once
uv run uvicorn app.main:app --reload   # API on http://localhost:8000
```

In a second terminal, the web app (proxies `/api` to the backend):

```bash
cd frontend
npm ci
npm run dev                       # http://localhost:5173
```

`setup` asks for members interactively, or reads `--file members.local.json` (git-ignored):
`{"members": [{"email": "...", "display_name": "..."}], "super_admin": "optional email"}`.
The optional super admin is managed only from the CLI:
`uv run python -m app.cli superadmin {create,activate,flatten,transfer,deactivate} [--email X]`.

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && npm run typecheck && npm run lint && npm run build
```

Backend tests use a separate `cic_test` database on the local Postgres.

## Deployment

The app ships as one Docker image (`Dockerfile`) with a Render blueprint (`render.yaml`) and a Neon Postgres database. Migrations run when the container starts. Steps, environment variables and costs: [docs/DEPLOY.md](docs/DEPLOY.md) and [docs/COSTS.md](docs/COSTS.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/SRS.md](docs/SRS.md) | Requirements |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Tables, rules and visibility policy |
| [docs/API.md](docs/API.md) | Public read API and app API |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Design decisions and why |
| [docs/DEPLOY.md](docs/DEPLOY.md), [docs/COSTS.md](docs/COSTS.md) | Deployment and hosting costs |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Version history |

Development process and team notes are in [docs/](docs/): [HACKATHON.md](docs/HACKATHON.md), [PLAN.md](docs/PLAN.md), [ENGINEERING.md](docs/ENGINEERING.md), [PHASE_LOG.md](docs/PHASE_LOG.md).

## License

[MIT](LICENSE)
