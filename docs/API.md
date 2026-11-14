# CIC Compass: API Contract

Two surfaces, kept separate on purpose:

| Surface | Path | Auth | Purpose |
|---|---|---|---|
| **Public read API** | `/api/v1/*` | API key | CIC's org dashboard, MCP server. Read-only, aggregates only. |
| **App API** | `/api/app/*` | Session cookie + CSRF | The web app's CRUD and actions. Not a public contract; may change. |

FastAPI generates OpenAPI at `/api/openapi.json`; the human docs page is `/api/docs` (Swagger UI, public API tag only in production) plus `docs/API_GUIDE.md` with curl examples.

---

## 1. Public read API (`/api/v1`)

### 1.1 Auth and errors

```
Authorization: Bearer cic_live_<32 random bytes, base64url>
```
- Keys are created in Settings → API keys, shown once, stored as SHA-256. Scope for all endpoints below: `read:aggregates`.
- `401` missing, malformed, unknown or revoked key. `403` wrong scope. `429` over 60 requests/minute (with `Retry-After`).
- Error body: `{"error": {"code": "unauthorized", "message": "..."}}`.
- Every response includes `as_of` (ISO timestamp) and `currency: "USD"`. Money is integer cents.
- **No donor PII ever**: response models contain no donor name, email, phone, note or id. A test asserts this against the OpenAPI schema.

### 1.2 Endpoints

| Method and path | Query | Returns |
|---|---|---|
| `GET /api/v1/summary` | `from`, `to` (dates, default last 12 months) | totals: gross, net, gift count, donor count, new donors, avg gift |
| `GET /api/v1/totals/by-period` | `from`, `to`, `period` = `month`/`quarter`/`year` | list of `{period_start, gross_cents, net_cents, gift_count, donor_count}` |
| `GET /api/v1/totals/by-program` | `from`, `to` | list of `{program, gross_cents, gift_count, donor_count}` |
| `GET /api/v1/totals/by-board-member` | `from`, `to` | list of `{board_member, donors_owned, gross_cents, open_reminders, contacts_logged, messages_sent}` |
| `GET /api/v1/retention` | `as_of`, `basis` = `rolling`/`calendar` | `{classes: {new: {donors, cents_cur, cents_prev}, ...}}` |
| `GET /api/v1/activity/recent` | `days` (1-90, default 30) | per day: gifts received, gross, contacts logged, messages sent |
| `GET /api/v1/health` | none | `{status: "ok"}` (no auth) |

Example:
```bash
curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "https://<host>/api/v1/totals/by-program?from=2025-11-01&to=2026-10-31"
```
```json
{
  "as_of": "2026-11-15T09:00:00-07:00",
  "currency": "USD",
  "from": "2025-11-01",
  "to": "2026-10-31",
  "items": [
    {"program": "AI Academy", "gross_cents": 1250000, "gift_count": 42, "donor_count": 31},
    {"program": "General", "gross_cents": 380000, "gift_count": 77, "donor_count": 60}
  ]
}
```

## 2. MCP server (`mcp_server/`)

Read-only, stdio transport, Python MCP SDK. Runs on the client machine (for example Claude Desktop) and calls the public API; it holds its own key in its env (`CIC_API_BASE`, `CIC_API_KEY`). No hosting cost.

| Tool | Maps to |
|---|---|
| `get_summary(from?, to?)` | `/api/v1/summary` |
| `get_totals_by_period(period, from?, to?)` | `/api/v1/totals/by-period` |
| `get_totals_by_program(from?, to?)` | `/api/v1/totals/by-program` |
| `get_totals_by_board_member(from?, to?)` | `/api/v1/totals/by-board-member` |
| `get_retention(as_of?, basis?)` | `/api/v1/retention` |
| `get_recent_activity(days?)` | `/api/v1/activity/recent` |

No write tools, by design (SRS API-6, API-7).

## 3. App API (`/api/app`), session-authenticated

All non-GET calls need header `X-CSRF-Token`. Authorization is decided in `authz/policy.py` (DATA_MODEL 3.6). Main routes:

| Area | Routes |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/invite/{token}/accept` |
| Members | `GET /members`, `POST /members/invite`, `POST /members/{id}/deactivate` |
| Governance | `GET /governance`, `PUT /governance/scope`, `POST /governance/flatten` |
| Imports | `POST /imports/preview` (multipart: `source`, `file`), `GET /imports/{id}`, `POST /imports/{id}/commit`, `POST /imports/{id}/reverse`, `GET /imports` |
| Review | `GET /reviews?status=open`, `POST /reviews/{id}/decide` (`link` + donor_id, `create_new`, `anonymous`) |
| Donors | `GET /donors?scope=mine\|all&q=&owner=&status=&program=&page=`, `POST /donors` (returns `409` with candidates when DED-6 finds a likely duplicate unless `confirm_new=true`), `GET /donors/{id}`, `PATCH /donors/{id}`, `DELETE /donors/{id}` (soft), `POST /donors/{id}/merge` |
| Timeline | `GET /donors/{id}/timeline` |
| Gifts | `POST /donors/{id}/gifts` (manual), `GET /gifts/unattributed` |
| Ownership | `POST /donors/{id}/reassign` (`to_user_id`, `reason`), `POST /members/{id}/move-donors` (super admin, bulk), `GET /donors/{id}/owner-history` |
| Contacts | `POST /donors/{id}/interactions` |
| Next steps | `PUT /donors/{id}/next-step`, `POST /next-steps/{id}/done` |
| Reminders | `GET /reminders?scope=mine` (To-do), `GET /reminders/needs-reassignment` |
| Messages | `POST /donors/{id}/messages` (create draft from template), `POST /messages/draft-quarterly` (bulk for my due donors), `PATCH /messages/{id}`, `POST /messages/{id}/approve`, `POST /messages/{id}/send`, `POST /messages/{id}/mark-sent`, `POST /messages/{id}/cancel`, `GET /messages?status=` |
| Digest | `POST /digest/send` |
| Reports | `GET /reports/summary`, `GET /reports/retention`, `GET /reports/funder/{donor_id}?format=html\|csv` |
| Settings | `GET/PUT /settings`, `GET/PUT /templates`, `GET/POST/PUT /programs`, `GET/POST/PUT /program-map`, `GET/POST /api-keys`, `POST /api-keys/{id}/revoke`, `GET/POST /program-outcomes` |
| Ops | `GET /healthz` (no auth), `POST /demo/reset` (only `DEMO_MODE=true`) |

Status codes: `400` validation, `401` no session, `403` policy denied, `404` not found or not visible, `409` state conflict (sending a draft, duplicate open draft, already-imported file, possible duplicate donor), `413` file too large, `415` wrong file type.
