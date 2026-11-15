# CIC Compass MCP server

A small, **read-only** [MCP](https://modelcontextprotocol.io) server that lets an AI assistant such
as Claude Desktop answer questions about Coding in Color's giving: totals, programs, board member
activity and donor retention. It runs on your own computer (stdio) and calls the public
`/api/v1` API with an API key, so it costs nothing to host.

**What it can see:** aggregates only. The API never returns donor names, emails, phone numbers,
notes or ids, so neither can this server. **What it can do:** read. It has no tools that create,
change, delete or send anything, and it only ever sends `GET` requests.

## Tools

| Tool | Arguments | API call |
|---|---|---|
| `get_summary` | `from_date?`, `to_date?` | `GET /api/v1/summary` |
| `get_totals_by_period` | `period` (`month`, `quarter`, `year`), `from_date?`, `to_date?` | `GET /api/v1/totals/by-period` |
| `get_totals_by_program` | `from_date?`, `to_date?` | `GET /api/v1/totals/by-program` |
| `get_totals_by_board_member` | `from_date?`, `to_date?` | `GET /api/v1/totals/by-board-member` |
| `get_retention` | `as_of?`, `basis` (`rolling`, `calendar`) | `GET /api/v1/retention` |
| `get_recent_activity` | `days` (1 to 90) | `GET /api/v1/activity/recent` |

Dates are `YYYY-MM-DD`. Money is integer US cents. The API's `from` and `to` parameters are
`from_date` and `to_date` here because `from` is a reserved word in Python.

## Set up

1. **Get an API key.** In the app: Settings → API keys → create a key. Copy it now; it is shown
   once. Keys can be revoked from the same page.
2. **Install [uv](https://docs.astral.sh/uv/)** (the only prerequisite) and clone this repository.
3. **Add the server to Claude Desktop.** Open Settings → Developer → Edit Config, and add:

```json
{
  "mcpServers": {
    "cic-compass": {
      "command": "uv",
      "args": ["run", "--directory", "C:/path/to/Karma.js-CodinginColor/mcp_server", "python", "server.py"],
      "env": {
        "CIC_API_BASE": "https://<your-cic-compass-host>",
        "CIC_API_KEY": "cic_live_..."
      }
    }
  }
}
```

   Use the real path to this folder (on macOS or Linux something like
   `/Users/you/Karma.js-CodinginColor/mcp_server`). `CIC_API_BASE` is the site address without
   `/api/v1`. Restart Claude Desktop; the tools appear under the plug icon.
4. **Ask**, for example: "How did giving by program compare this year?" or "How many donors lapsed
   in the last 12 months?"

The key lives only in that config file on your computer. Do not commit it or paste it into chat.

## Run and test it yourself

```bash
cd mcp_server
uv sync
CIC_API_BASE=http://localhost:8000 CIC_API_KEY=cic_live_... uv run python server.py   # waits on stdin
uv run pytest        # 20 tests; no network or database needed
uv run ruff check . && uv run mypy server.py
```

To try it with the official inspector: `npx @modelcontextprotocol/inspector uv run python server.py`
(with the two environment variables set).

## Errors you may see

| Message | What to do |
|---|---|
| The API key was rejected | Check `CIC_API_KEY`, or create a new key; revoked keys stop working at once |
| Rate limit reached | The API allows 60 requests a minute per key; wait the number of seconds shown |
| Could not reach the CIC Compass API | Check `CIC_API_BASE` and your connection (the hosted site may take about a minute to wake up) |

## Notes for maintainers

- The `mcp` package is pinned to an exact version at least 14 days old (`uv.lock`,
  `exclude-newer`), like every dependency in this project.
- Adding a tool means adding a matching `GET` endpoint to `/api/v1` first. Keep the rule that no tool
  writes anything (SRS API-6, API-7, D-113); `tests/test_server.py` fails if a tool is not marked
  read-only or if any request other than `GET` is made.
