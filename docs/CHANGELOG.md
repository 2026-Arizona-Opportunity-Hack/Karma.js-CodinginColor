# Changelog

Notable changes to CIC Compass, newest first. Versions follow [Semantic Versioning](https://semver.org/) while the app is pre-1.0.

## 0.1.0 (2026-11-14): foundation

- FastAPI backend with PostgreSQL 16, Alembic migrations, typed errors, a Phoenix-time injectable clock and a `/healthz` endpoint.
- Tables for board members, governance (flat by default, optional super admin), sessions, invites, API keys and an append-only audit log; governance rules are enforced by database constraints.
- Individual logins: Argon2id password hashes, hashed session tokens in `HttpOnly` cookies, CSRF protection on state-changing requests, login rate limiting, audited login and logout.
- Operator CLI (`python -m app.cli`) to create board members and manage the optional super admin.
- React web app shell: login page and main navigation (Dashboard, Donors, Import, Review, Messages, Reports, Settings).
- Single Docker image serving the API and the web app; GitHub Actions CI (lint, types, tests, build, secret scan); Render blueprint for deployment.
