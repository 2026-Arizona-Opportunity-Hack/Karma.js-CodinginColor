# Deploying CIC Compass (Render + Neon)

One Docker web service on Render and a Neon Postgres database. **$0/month** on Render's free instance; about $7/month on Starter for always-on production. Prices and sources: [COSTS.md](COSTS.md).

`render.yaml` defines the service. The container runs `alembic upgrade head` on start, then the app, so a deploy migrates the database by itself.

Run a single uvicorn process. Import previews are kept in memory between Preview and Commit, so multiple workers or instances break commit. A restart or redeploy clears open previews and the uploader must upload again.

## First deploy

1. **Neon:** in the project, click **Connect**, turn **Connection pooling off**, copy the connection string (`postgresql://...?sslmode=require...`). The app accepts `postgres://` and `postgresql://` URLs.
2. **Render:** New → Blueprint → pick this repo, branch `main`. `render.yaml` creates the `cic-compass` service. Paste the Neon string into `DATABASE_URL` when asked; leave `RESEND_API_KEY` and `MAIL_FROM` empty (messaging stays in dry-run).
3. Deploy, then check `https://<service>.onrender.com/healthz` returns `{"status":"ok"}`.
4. **Create board members** from a machine with the repo (nothing secret is committed). Put names in the git-ignored `members.local.json` at the repo root:
   ```bash
   cd backend
   DATABASE_URL='postgresql://...neon...' uv run python -m app.cli setup --file ../members.local.json
   ```
   The command prints each initial password once. On a paid Render instance the dashboard Shell works too: `python -m app.cli setup`.
5. Log in on the Render URL in a private window as two different members; each should see their own name.

## Environment variables

| Variable | Where | Notes |
|---|---|---|
| `DATABASE_URL` | Render dashboard | Neon direct connection string; secret |
| `APP_ENV`, `COOKIE_SECURE`, `MESSAGING_MODE`, `DEMO_MODE` | `render.yaml` | `prod`, `true`, `dry_run`, `false` |
| `RESEND_API_KEY`, `MAIL_FROM` | Render dashboard | only with `MESSAGING_MODE=live`; secret |

## Free-instance behaviour

Render's free web service sleeps after 15 minutes without traffic and takes about a minute to wake; Neon's free compute sleeps after 5 minutes idle. Open the URL a minute before a demo. To keep it always on, change `plan: free` to `plan: starter` in `render.yaml`.

## Housekeeping

- Rotate the Neon password (Roles → reset password) if the connection string was ever shared, then update `DATABASE_URL` in Render.
- Neon Free keeps 6 hours of history and has no instant restore; take a `pg_dump` before risky changes.
