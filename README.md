# CIC Compass

A donor stewardship app for [Coding in Color](https://www.ohack.dev/nonprofit/YIXYdYCoxIZC08uQ5DL3) (CIC). It keeps donors and funders in one place so nobody has to hunt through exports from several giving platforms to see who gave, when, and who last got in touch.

Built for CIC's [Donor & Funder Relationship Platform](https://www.ohack.dev/project/e26932c0df1b11f189a8dead68f07eb5) problem statement at the ASU Fall Hackathon 2026 by team Karma.js. Open source under the MIT license.

**Current version:** 0.1.0. Backend implementation and verification status: [phase log](docs/PHASE_LOG.md). See the [changelog](docs/CHANGELOG.md).

## What it does

**Available now**
- Individual board-member accounts with secure login, sessions and CSRF protection.
- A flat hierarchy by default, with an optional single super admin created and removed in the app (see Governance).
- An audit log of logins and governance changes.
- CSV/XLSX import preview and commit, with a field-by-field confirmation dialog for spreadsheet donor updates; backend batch history, soft reversal, file/gift deduplication and balanced donor ownership.
- Backend donor identity reviews and anonymous-gift attribution, with authorization and audit records.
- A web app shell with navigation for Dashboard, Donors, Import, Review, Messages, Reports and Settings.

Imports use assumed source layouts documented in [IMPORT_FORMATS.md](docs/IMPORT_FORMATS.md).
Preview state lasts 20 minutes in one backend process; expiration or a restart requires re-upload.
Committed batches and their history are stored in PostgreSQL. Employer matches remain org revenue;
employee totals and retention count only employee donations (D-127). The Import screen supports
upload, preview and commit; every proposed donor field starts unchecked. The identity Review
screen remains lane B's work. Backend endpoints also appear in the app's API documentation.

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

### Governance: the optional super admin

The board starts **flat**: every active member has equal permissions. On the Members page:

- **Nominate.** While flat, any active member can click *Nominate super admin* and pick an active member (themselves included). A **different** member must confirm within 72 hours; the nominator cannot. Either the nominator or the nominee can cancel. Unconfirmed nominations expire.
- **Remove.** Only the super admin can click *Remove my super admin role* and type `REMOVE`. The org becomes flat, the reassignment scope returns to `anyone`, and the person stays a member and keeps their donors. A dormant super admin can remove the role too.
- API keys, including full-access keys, can never nominate, confirm, cancel or remove (403). Every step is written to the audit log.

**Break-glass:** the setup command still works when nobody can use the app, and can create, activate, transfer, flatten or deactivate the role:
`uv run python -m app.cli superadmin {create,activate,flatten,transfer,deactivate} [--email X]`.

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && npm run typecheck && npm run lint && npm run build
```

Backend tests use a separate `cic_test` database on the local Postgres.

## Deployment

The app ships as one Docker image (`Dockerfile`) with a Render blueprint (`render.yaml`) and a Neon Postgres database. Migrations run when the container starts. Steps, environment variables and costs: [docs/DEPLOY.md](docs/DEPLOY.md) and [docs/COSTS.md](docs/COSTS.md).

## Security

- Passwords are Argon2id hashed; sessions use `HttpOnly` cookies with CSRF protection on every write.
- **API keys.** `cic_live_` keys on `/api/v1` are read-only and aggregate-only: totals and counts, never donor names, emails or phones.
- **Full-access keys exist.** A `cic_full_` key grants full read and write access to every `/api/app` route as the member who created it, including donor contact details. Governance and key management stay off limits. Keys are shown once, stored only as a hash, expire after 90 days, are rate limited, and every change they make is audited with the key's id. Treat one like a password: share it only with apps you trust and revoke it when done. See [API guide](docs/API_GUIDE.md#10-full-access-keys).
- No secrets in git: real values live in `.env`, and a pre-commit guard and CI secret scan enforce it.

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
