"""The MCP server is read-only, calls the REST API with its own key, and never leaks the key."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server

KEY = "cic_live_" + "k" * 43
EXPECTED_TOOLS = {
    "get_summary",
    "get_totals_by_period",
    "get_totals_by_program",
    "get_totals_by_board_member",
    "get_retention",
    "get_recent_activity",
}


class Recorder:
    def __init__(self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None):
        self.requests: list[httpx.Request] = []
        self.status, self.body, self.headers = (
            status,
            body or {"currency": "USD"},
            headers or {},
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body, headers=self.headers)


def make(rec: Recorder):
    api = server.ApiClient("https://cic.example.org/", KEY, transport=httpx.MockTransport(rec))
    return server.build_server(api)


def call(mcp, name: str, args: dict[str, Any] | None = None) -> Any:
    return asyncio.run(mcp.call_tool(name, args or {}))


def test_exactly_the_six_read_tools_and_nothing_that_writes() -> None:
    tools = asyncio.run(make(Recorder()).list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS
    for t in tools:
        assert t.annotations is not None
        assert t.annotations.read_only_hint is True and t.annotations.destructive_hint is False
    assert not any(
        w in t.name for t in tools for w in ("create", "update", "delete", "send", "set")
    )


def test_tool_schemas_expose_only_dates_period_basis_and_days() -> None:
    tools = {t.name: t for t in asyncio.run(make(Recorder()).list_tools())}

    def props(n: str) -> set[str]:
        return set(tools[n].input_schema["properties"])

    assert props("get_summary") == {"from_date", "to_date"}
    assert props("get_totals_by_period") == {"period", "from_date", "to_date"}
    assert props("get_retention") == {"as_of", "basis"}
    assert props("get_recent_activity") == {"days"}


@pytest.mark.parametrize(
    "tool,args,path,query",
    [
        ("get_summary", {}, "/api/v1/summary", {}),
        ("get_summary", {"from_date": "2026-01-01", "to_date": "2026-02-01"},
         "/api/v1/summary", {"from": "2026-01-01", "to": "2026-02-01"}),
        ("get_totals_by_period", {}, "/api/v1/totals/by-period", {"period": "month"}),
        ("get_totals_by_period", {"period": "quarter", "from_date": "2026-01-01"},
         "/api/v1/totals/by-period", {"period": "quarter", "from": "2026-01-01"}),
        ("get_totals_by_program", {"to_date": "2026-03-01"},
         "/api/v1/totals/by-program", {"to": "2026-03-01"}),
        ("get_totals_by_board_member", {}, "/api/v1/totals/by-board-member", {}),
        ("get_retention", {}, "/api/v1/retention", {"basis": "rolling"}),
        ("get_retention", {"as_of": "2026-11-15", "basis": "calendar"},
         "/api/v1/retention", {"as_of": "2026-11-15", "basis": "calendar"}),
        ("get_recent_activity", {}, "/api/v1/activity/recent", {"days": "30"}),
        ("get_recent_activity", {"days": 7}, "/api/v1/activity/recent", {"days": "7"}),
    ],
)  # fmt: skip
def test_each_tool_makes_one_get_with_the_key(tool, args, path, query) -> None:
    rec = Recorder(body={"currency": "USD", "items": []})
    result = call(make(rec), tool, args)
    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert req.method == "GET" and req.url.path == path
    assert dict(req.url.params) == query
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert "USD" in json.dumps(result, default=str)


def test_only_get_is_ever_sent() -> None:
    rec = Recorder()
    mcp = make(rec)
    for name in EXPECTED_TOOLS:
        call(mcp, name)
    assert {r.method for r in rec.requests} == {"GET"}


@pytest.mark.parametrize(
    "status,fragment",
    [(401, "key was rejected"), (403, "not allowed"), (429, "Try again in 42 seconds"),
     (400, "not valid: bad range"), (500, "answered 500")],
)  # fmt: skip
def test_errors_are_explained_and_never_contain_the_key(status, fragment) -> None:
    rec = Recorder(
        status=status,
        body={"error": {"code": "x", "message": "bad range"}},
        headers={"Retry-After": "42"},
    )
    with pytest.raises(ToolError) as err:
        call(make(rec), "get_summary")
    assert fragment in str(err.value) and KEY not in str(err.value)


def test_network_failure_is_reported_without_details() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect with {KEY}")

    api = server.ApiClient("https://cic.example.org", KEY, transport=httpx.MockTransport(boom))
    with pytest.raises(ToolError) as err:
        call(server.build_server(api), "get_summary")
    assert KEY not in str(err.value) and "Could not reach" in str(err.value)


def test_missing_environment_stops_with_a_helpful_message(monkeypatch) -> None:
    monkeypatch.delenv("CIC_API_BASE", raising=False)
    monkeypatch.delenv("CIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        server.main()
    assert "CIC_API_BASE" in str(e.value) and KEY not in str(e.value)
