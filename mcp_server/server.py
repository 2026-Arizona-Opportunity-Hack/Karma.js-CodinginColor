"""Read-only MCP server for the CIC Compass public API (API-6, D-113).

Runs on the client machine over stdio (for example in Claude Desktop). It only makes GET
requests to `/api/v1`, using a key from its own environment, and exposes no write tools.
The API returns aggregates only, so nothing here can reach donor names or contact details.

    CIC_API_BASE   https://<host>      (no trailing /api/v1)
    CIC_API_KEY    cic_live_...        (Settings -> API keys in the app)
"""

import os
import sys
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
TIMEOUT_SECONDS = 20.0


class ApiClient:
    """GET-only client. The key is sent as a bearer token and never appears in errors."""

    def __init__(self, base: str, key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(
            base_url=base.rstrip("/"),
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def get(self, path: str, **params: str | int | None) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        try:
            r = self._http.get(f"/api/v1{path}", params=query)
        except httpx.HTTPError as e:
            raise ToolError(f"Could not reach the CIC Compass API ({type(e).__name__}).") from None
        if r.status_code == 200:
            body: dict[str, Any] = r.json()
            return body
        raise ToolError(_explain(r))


def _explain(r: httpx.Response) -> str:
    try:
        message = str(r.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        message = ""
    if r.status_code == 401:
        return "The API key was rejected. Check CIC_API_KEY, or create a new key in the app."
    if r.status_code == 403:
        return "This API key is not allowed to read aggregates."
    if r.status_code == 429:
        wait = r.headers.get("Retry-After", "60")
        return f"Rate limit reached (60 requests a minute). Try again in {wait} seconds."
    if r.status_code == 400:
        return f"The request was not valid: {message}" if message else "The request was not valid."
    return f"The CIC Compass API answered {r.status_code}."


def build_server(api: ApiClient) -> MCPServer:
    mcp = MCPServer(
        "cic-compass",
        instructions=(
            "Aggregate giving numbers for Coding in Color. Money is in integer US cents. "
            "Dates are YYYY-MM-DD. This server is read-only and returns no donor details."
        ),
    )

    @mcp.tool(annotations=READ_ONLY)
    def get_summary(from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
        """Totals for a date range: gross, net, gift count, donor count, new donors and average
        gift. Defaults to the last 12 months."""
        return api.get("/summary", **{"from": from_date}, to=to_date)

    @mcp.tool(annotations=READ_ONLY)
    def get_totals_by_period(
        period: Literal["month", "quarter", "year"] = "month",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Giving per month, quarter or year: gross, net, gift count and donor count."""
        return api.get("/totals/by-period", period=period, **{"from": from_date}, to=to_date)

    @mcp.tool(annotations=READ_ONLY)
    def get_totals_by_program(
        from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, Any]:
        """Giving per program (AI Academy, Summer Camp and so on)."""
        return api.get("/totals/by-program", **{"from": from_date}, to=to_date)

    @mcp.tool(annotations=READ_ONLY)
    def get_totals_by_board_member(
        from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, Any]:
        """Per board member: donors owned, their giving, contacts logged and messages sent."""
        return api.get("/totals/by-board-member", **{"from": from_date}, to=to_date)

    @mcp.tool(annotations=READ_ONLY)
    def get_retention(
        as_of: str | None = None, basis: Literal["rolling", "calendar"] = "rolling"
    ) -> dict[str, Any]:
        """Donor retention classes (new, reactivated, increased, same, decreased, lapsed) with
        donor counts and dollars, rolling 12 months or calendar year."""
        return api.get("/retention", as_of=as_of, basis=basis)

    @mcp.tool(annotations=READ_ONLY)
    def get_recent_activity(days: int = 30) -> dict[str, Any]:
        """Per day for the last 1 to 90 days: gifts received, gross, contacts logged, messages
        sent."""
        return api.get("/activity/recent", days=days)

    return mcp


def main() -> None:
    base, key = os.environ.get("CIC_API_BASE", ""), os.environ.get("CIC_API_KEY", "")
    if not base or not key:
        sys.exit("Set CIC_API_BASE and CIC_API_KEY (see mcp_server/README.md).")
    build_server(ApiClient(base, key)).run("stdio")


if __name__ == "__main__":
    main()
