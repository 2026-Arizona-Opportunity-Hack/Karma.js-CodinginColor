"""Security headers and request rate limits (NFR-1). Plain ASGI, no body is read.

Headers go on every response. The CSP is strict for the app and the API; only the Swagger docs
page (`/api/docs`) is allowed to load its viewer from jsDelivr. Rate limits are per client IP
and counted in memory: Render runs one worker, so they are exact there and reset on restart.
Login has its own, tighter bucket on top of the failed-login lockout (AUTH-6).
"""

import ipaddress
import json
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

APP_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
DOCS_CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: "
    "https://fastapi.tiangolo.com; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "frame-ancestors 'none'"
)
HEADERS = {
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}

LOGIN_PATH = "/api/app/auth/login"
LOGIN_LIMIT = 20  # per IP per minute
APP_LIMIT = 300  # per IP per minute, all /api/app routes
WINDOW_SECONDS = 60.0


class Limiter:
    """Sliding window per key. `check` returns None if allowed, else seconds to wait."""

    def __init__(self, limit: int, window: float = WINDOW_SECONDS) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, now: float) -> int | None:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(1, math.ceil(hits[0] + self.window - now))
        hits.append(now)
        return None


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    host = client[0] if client else ""
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return "unknown"


class SecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        rate_limits: bool = True,
        login_limit: int = LOGIN_LIMIT,
        app_limit: int = APP_LIMIT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.rate_limits = rate_limits
        self.login = Limiter(login_limit)
        self.general = Limiter(app_limit)
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        if self.rate_limits and path.startswith("/api/app/"):
            wait = self._wait(scope, path)
            if wait is not None:
                await self._too_many(send, wait)
                return
        csp = DOCS_CSP if path == "/api/docs" else APP_CSP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message["headers"]}
                extra = {**HEADERS, "content-security-policy": csp}
                message["headers"] = [
                    *message["headers"],
                    *(
                        (k.encode(), v.encode())
                        for k, v in extra.items()
                        if k.encode() not in present
                    ),
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _wait(self, scope: Scope, path: str) -> int | None:
        ip, now = _client_ip(scope), self.clock()
        if path == LOGIN_PATH and scope["method"] == "POST":
            wait = self.login.check(ip, now)
            if wait is not None:
                return wait
        return self.general.check(ip, now)

    async def _too_many(self, send: Send, wait: int) -> None:
        body = json.dumps(
            {"error": {"code": "too_many_requests", "message": "Too many requests; slow down."}}
        ).encode()
        headers = {
            "content-type": "application/json",
            "content-length": str(len(body)),
            "retry-after": str(wait),
            "cache-control": "no-store",
            **HEADERS,
            "content-security-policy": APP_CSP,
        }
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            }
        )
        await send({"type": "http.response.body", "body": body})
