# CIC Compass API guide

For whoever connects CIC's own dashboard, spreadsheet or scripts to CIC Compass. You do not need
to know how the app is built. The API answers questions like "how much did we raise per program last
year?" and "how many donors did we keep?". Every example below was run against a real local copy of
the app, with made-up data.

**What you get:** totals and counts. **What you never get:** donor names, emails, phone numbers, notes
or ids. The public API cannot reveal them even by mistake: a test fails the build if a donor field
ever appears in it. It is also read-only, so it cannot change anything.

Contents: [get a key](#1-get-a-key) · [first call](#2-make-your-first-call) ·
[how numbers work](#3-how-the-numbers-work) · [endpoints](#4-endpoints) ·
[retention](#5-retention-explained) · [errors and limits](#6-errors-and-limits) ·
[keeping keys safe](#7-keeping-keys-safe) · [use it from Claude](#8-use-it-from-claude) ·
[interactive docs](#9-interactive-docs-and-machine-readable-spec)

---

## 1. Get a key

Keys are created by a signed-in board member. The easiest way is **Settings → API keys** in the app.
The `curl` commands below do the same thing (Swagger at `/api/docs` works too).

```bash
export CIC_API_BASE="https://cic-compass.onrender.com"

# 1. Sign in as yourself. This stores your session in a temporary file.
curl -s -c session.txt -H "Content-Type: application/json"   -d '{"email":"you@example.org","password":"YOUR PASSWORD"}' "$CIC_API_BASE/api/app/auth/login"

# 2. Create a key. Writes need the CSRF token from the cookie file.
CSRF=$(grep cic_csrf session.txt | awk '{print $7}')
curl -s -b session.txt -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json"   -d '{"name":"Dashboard"}' "$CIC_API_BASE/api/app/api-keys"
```
```json
{"id": 1, "name": "Dashboard", "prefix": "cic_live_SIGy", "scopes": ["read:aggregates"],
 "created_at": "2026-11-15T04:10:50.121008Z", "last_used_at": null, "revoked_at": null,
 "key": "cic_live_SIGyth...the rest of the key..."}
```

The `key` value is your API key: `cic_live_` followed by 43 letters, digits, `-` and `_`.

- **Copy it now.** It is shown once. The app stores only a fingerprint, so nobody (including us) can
  show it to you again. If you lose it, create a new one and revoke the old one.
- Delete `session.txt` afterwards (it holds your login session).
- **List keys** (name, first characters, when last used, whether revoked, never the key itself):
  `curl -s -b session.txt "$CIC_API_BASE/api/app/api-keys"`
- **Revoke a key** (use its `id`): `curl -s -b session.txt -H "X-CSRF-Token: $CSRF" -X POST "$CIC_API_BASE/api/app/api-keys/1/revoke"`

**Prefer not to use `curl`?** Whoever runs the server can do the same with the operator command, from
the `backend` folder (it prints the key once; the email is the board member it is recorded for):

```bash
python -m app.cli apikey create --name Dashboard --email you@example.org
python -m app.cli apikey list
python -m app.cli apikey revoke 1
```

Who can create keys: any board member while the board is flat; only the super admin while one is
active. Name each key after who uses it, for example "Dashboard".

## 2. Make your first call

Set two variables once (use the real address of your CIC Compass site):

```bash
export CIC_API_BASE="https://cic-compass.onrender.com"
export CIC_API_KEY="cic_live_..."          # the key from step 1
```

Check the service is up (no key needed), then ask for the totals by program:

```bash
curl -s "$CIC_API_BASE/api/v1/health"
# {"status":"ok"}

curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "$CIC_API_BASE/api/v1/totals/by-program?from=2025-11-01&to=2026-11-15"
```

```json
{
  "as_of": "2026-11-15T04:08:01.472074Z",
  "currency": "USD",
  "from": "2025-11-01",
  "to": "2026-11-15",
  "items": [
    {"program": "AI Academy", "gross_cents": 200000, "gift_count": 2, "donor_count": 1},
    {"program": "Summer Camp", "gross_cents": 25000, "gift_count": 1, "donor_count": 1},
    {"program": "General", "gross_cents": 10000, "gift_count": 1, "donor_count": 0}
  ]
}
```

Tip: pipe through `jq` (`| jq .`) to read it comfortably. If the hosted site has been idle it can take
about a minute to wake up on the first call.

## 3. How the numbers work

- **Money is whole cents.** `gross_cents: 200000` is **$2,000.00**. Divide by 100 to show dollars.
  Currency is always `"USD"`.
- **`as_of`** is when the answer was computed (UTC). Every response has it, so a dashboard can show
  "data as of".
- **Dates are `YYYY-MM-DD`** and mean the calendar day in Phoenix (Arizona) time.
- **`from` / `to`** are inclusive. Leave both out and you get the **last 12 months ending today**.
  `from` cannot be after `to`, and a range is limited to 10 years.
- **Gross, net, fee.** *Gross* is what the donor paid, *net* is what CIC received after platform fees
  (net = gross − fee).
- **Which gifts count.** Gifts that are linked to a donor, and anonymous gifts (for example a Benevity
  row with no donor details). Gifts still waiting for a human to confirm who gave, and deleted
  gifts, are left out. Employer matching gifts count like any other gift.
- **`donor_count`** counts identified donors. Anonymous gifts add to the money and `gift_count` but not
  to `donor_count`, which is why a program can show gifts with `"donor_count": 0`.

## 4. Endpoints

All endpoints are `GET`, live under `/api/v1`, and (except `health`) need the header
`Authorization: Bearer <your key>`.

| Endpoint | What it answers |
|---|---|
| `/summary` | One set of headline totals for a date range |
| `/totals/by-period` | Giving per month, quarter or year |
| `/totals/by-program` | Giving per program |
| `/totals/by-board-member` | Each board member's donors, their giving, and the work logged |
| `/retention` | How many donors were kept, won, grew or lapsed |
| `/activity/recent` | A day-by-day log for the last 1 to 90 days |
| `/health` | `{"status":"ok"}`, no key needed |

### `GET /summary`

Query: `from`, `to` (optional).

```bash
curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "$CIC_API_BASE/api/v1/summary?from=2025-11-01&to=2026-10-31"
```
```json
{
  "as_of": "2026-11-15T04:08:00.910316Z", "currency": "USD",
  "from": "2025-11-01", "to": "2026-10-31",
  "gross_cents": 150000, "net_cents": 145500, "gift_count": 1,
  "donor_count": 1, "new_donors": 1, "avg_gift_cents": 150000
}
```

`new_donors` counts donors whose **first ever** gift falls inside the range. `avg_gift_cents` is
gross divided by gift count, rounded to the nearest cent (0 when there are no gifts).

### `GET /totals/by-period`

Query: `period` = `month` (default), `quarter` or `year`; `from`, `to`.

```bash
curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "$CIC_API_BASE/api/v1/totals/by-period?period=quarter&from=2025-11-01&to=2026-11-15"
```
```json
{
  "as_of": "2026-11-15T04:08:01.200593Z", "currency": "USD",
  "from": "2025-11-01", "to": "2026-11-15", "period": "quarter",
  "items": [
    {"period_start": "2026-10-01", "gross_cents": 235000, "net_cents": 230500,
     "gift_count": 4, "donor_count": 2}
  ]
}
```

`period_start` is the first day of the month, quarter or year. Periods with no gifts are not listed.
A donor who gave twice in one period counts once in that period's `donor_count`.

### `GET /totals/by-program`

Query: `from`, `to`. Example and response are in [step 2](#2-make-your-first-call). Largest program
first. Gifts whose campaign has no program are counted under **General**.

### `GET /totals/by-board-member`

Query: `from`, `to`. Board members' display names are the only names this API returns.

```bash
curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "$CIC_API_BASE/api/v1/totals/by-board-member?from=2025-11-01&to=2026-11-15"
```
```json
{
  "as_of": "2026-11-15T04:08:01.734744Z", "currency": "USD",
  "from": "2025-11-01", "to": "2026-11-15",
  "items": [
    {"board_member": "Diana Rivera", "donors_owned": 2, "gross_cents": 200000,
     "open_reminders": 0, "contacts_logged": 1, "messages_sent": 0},
    {"board_member": "Sam Ortiz", "donors_owned": 1, "gross_cents": 25000,
     "open_reminders": 0, "contacts_logged": 0, "messages_sent": 0}
  ]
}
```

- `donors_owned`: donors that member owns **today** (not limited to the date range).
- `gross_cents`: gifts from those donors inside the range.
- `contacts_logged` and `messages_sent`: what that member did inside the range.
- `open_reminders`: **always 0 for now**. The field is reserved for the reminders feature.

### `GET /retention`

Query: `as_of` (a date, default today), `basis` = `rolling` (default) or `calendar`. See
[retention explained](#5-retention-explained).

```bash
curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "$CIC_API_BASE/api/v1/retention?as_of=2026-11-15"
```
```json
{
  "as_of": "2026-11-15T04:08:02.006067Z", "currency": "USD",
  "retention_date": "2026-11-15", "basis": "rolling",
  "classes": {
    "new":         {"donors": 2, "cents_cur": 225000, "cents_prev": 0},
    "reactivated": {"donors": 0, "cents_cur": 0, "cents_prev": 0},
    "increased":   {"donors": 0, "cents_cur": 0, "cents_prev": 0},
    "same":        {"donors": 0, "cents_cur": 0, "cents_prev": 0},
    "decreased":   {"donors": 0, "cents_cur": 0, "cents_prev": 0},
    "lapsed":      {"donors": 1, "cents_cur": 0, "cents_prev": 80000}
  }
}
```

Here `as_of` is the time the answer was computed, as in every response, and `retention_date` is the
date you asked about (the query parameter is also called `as_of`). All six classes are always present.

### `GET /activity/recent`

Query: `days`, 1 to 90 (default 30). One entry per day, oldest first, including days with nothing.

```bash
curl -s -H "Authorization: Bearer $CIC_API_KEY" \
  "$CIC_API_BASE/api/v1/activity/recent?days=7"
```
```json
{
  "as_of": "2026-11-15T04:08:10.747328Z", "currency": "USD", "days": 7,
  "items": [
    {"day": "2026-11-09", "gifts_received": 0, "gross_cents": 0, "contacts_logged": 1, "messages_sent": 0},
    {"day": "2026-11-10", "gifts_received": 1, "gross_cents": 10000, "contacts_logged": 0, "messages_sent": 0}
  ]
}
```

(Shortened here; the real answer lists all 7 days.)

## 5. Retention explained

Retention compares what each donor gave in two windows and puts every donor in one class.
With the default **rolling** basis and an `as_of` date *T*, the current window is the 365 days ending
on *T*, and the previous window is the 365 days before that. With **calendar**, they are the calendar
year of *T* and the year before.

| Class | Meaning |
|---|---|
| `new` | Gave now, gave nothing in the previous window, and never gave before that |
| `reactivated` | Gave now, nothing in the previous window, but had given earlier than that |
| `increased` | Gave in both windows, more now |
| `same` | Gave in both windows, the same total |
| `decreased` | Gave in both windows, less now |
| `lapsed` | Gave in the previous window, nothing now |

`cents_cur` and `cents_prev` add up what that class's donors gave in each window. Only gifts linked to
a donor count (anonymous gifts cannot be tracked as a person), and deleted or merged donors are left
out. The default is rolling because a calendar year would show donors who gave in November as
"lapsed" every January.

## 6. Errors and limits

Every error has the same shape:

```json
{"error": {"code": "unauthorized", "message": "Missing, invalid or revoked API key."}}
```

| Status | `code` | Meaning and what to do |
|---|---|---|
| 400 | `invalid` | A parameter is wrong (bad date, `from` after `to`, `days` outside 1 to 90). The message says which. |
| 401 | `unauthorized` | No key, a malformed or unknown key, or a revoked key. Check the header is `Authorization: Bearer cic_live_...`. |
| 403 | `forbidden` | The key exists but is not allowed to read aggregates. |
| 429 | `too_many_requests` | More than **60 requests in a minute** with this key. Wait the number of seconds in the `Retry-After` header. |

The limit is per key, so give each tool its own key. A dashboard that refreshes a few times a minute
will never notice it; for more, cache the results on your side (the numbers only change when someone
imports data or logs activity).

```bash
curl -s -i -H "Authorization: Bearer $CIC_API_KEY" "$CIC_API_BASE/api/v1/totals/by-program"
# HTTP/1.1 429 Too Many Requests
# retry-after: 43
# {"error":{"code":"too_many_requests","message":"Rate limit is 60 requests per minute."}}
```

## 7. Keeping keys safe

- Treat a key like a password: keep it in a password manager or your tool's secret settings. Never put
  it in a spreadsheet, a public repository, a screenshot or a chat message.
- One key per tool or person, named clearly, so you can revoke one without breaking the rest.
- **To revoke:** use the `revoke` command in [step 1](#1-get-a-key). It stops working immediately (the
  next call gets `401`). Revoke a key as soon as someone who had it leaves, or you think it leaked.
- The key can only read totals and counts, so a leaked key cannot change data or expose donors, but it
  still reveals CIC's giving numbers.
- If you rotate keys: create the new key, switch your tool over, then revoke the old one.

## 8. Use it from Claude

CIC Compass includes a small read-only connector so Claude Desktop can answer questions such as "which
program raised the most this year?" using this same API and key. Setup takes a few minutes: see
[`mcp_server/README.md`](../mcp_server/README.md).

## 9. Interactive docs and machine-readable spec

- **Try it in a browser:** `$CIC_API_BASE/api/docs` (Swagger UI). The page lists every route of the
  app; the ones for this guide are under `/api/v1` with the `v1` tag. Use **Authorize** and paste your
  key to send `/api/v1` calls from the page. Routes under `/api/app` are for the web app only, need a login, and
  may change without notice. They are not part of this API.
- **Spec file:** `$CIC_API_BASE/api/openapi.json` is the OpenAPI document, which tools such as
  Postman, Power BI, or code generators can import.

## 10. Full-access keys

A **full-access key** (`cic_full_...`) lets another app read and change everything the web app can,
as the board member who created the key, with no login. It is separate from the read-only keys above:
those stay on `/api/v1` and cannot touch donors.

> **Warning:** anyone with this key can read and change all donor data, including contact details.
> Share only with apps you trust; revoke when done.

**Create one** in the app under **Settings → API keys → Full access**, or with the operator CLI:
`python -m app.cli apikey create --scope full_access --name "My app" --as you@example.org`.
The key is shown once. It expires after 90 days (the CLI takes `--expires-days N`, `0` = never).
While a super admin is active, only they can create keys.

**Use it** by sending the key on every request. There are no cookies and no CSRF token:

```bash
export CIC_API_BASE="https://cic-compass.onrender.com"
export CIC_FULL_KEY="paste the cic_full_ key here"

# List donors
curl -s -H "Authorization: Bearer $CIC_FULL_KEY" "$CIC_API_BASE/api/app/donors"

# Create a donor
curl -s -H "Authorization: Bearer $CIC_FULL_KEY" -H "Content-Type: application/json"   -d '{"kind":"person","display_name":"Ada Lovelace","email":"ada@example.org"}'   "$CIC_API_BASE/api/app/donors"

# Log a contact (use an id from the list above)
curl -s -H "Authorization: Bearer $CIC_FULL_KEY" -H "Content-Type: application/json"   -d '{"kind":"call","summary":"Thanked her for the gift."}'   "$CIC_API_BASE/api/app/donors/42/interactions"
```

Every route, with its fields and errors, is listed at `$CIC_API_BASE/api/docs` (read it there, then call the routes with
`curl` or your app). Rules to know:

- You can do whatever the creating member can, on every donor, and nothing more. Governance (flatten,
  reassignment scope, super admin) and API-key management are refused with `403`, so a key cannot
  create or revoke keys. Revoke from Settings or the CLI.
- `401` for a missing, wrong, revoked or expired key, or if the member who made it was deactivated.
  `429` after 300 requests in a minute, with `Retry-After`.
- Browsers on any website may call `/api/app` with the key in the `Authorization` header. Cookies are
  never sent across sites. Do not put a full-access key in a web page or app that other people can
  open: anyone who sees it holds it.
- `/api/app` is **not a versioned public contract**. Routes and fields can change; pin to what you
  tested and re-check after updates. Each change a key makes is audited with the key's id.

## Stability

`/api/v1` is the stable public surface: fields may be added over time, but existing fields keep their
names and meanings. If something here does not match what the API returns, the API is right; please tell
the team so this guide can be fixed.
