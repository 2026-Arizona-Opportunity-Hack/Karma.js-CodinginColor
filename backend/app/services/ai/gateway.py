"""Minimal client for the OHack AI gateway (OpenAI-style chat completions).

Only the system prompt and the member's sentence are sent. Prompt and reply text are never
logged or stored, and the donor list is never included (AST-3)."""

from typing import Protocol

import httpx

from app.settings import get_settings

TIMEOUT_SECONDS = 15.0


class GatewayError(Exception):
    """The gateway is not configured, timed out, or answered with something unusable."""


class Gateway(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class HttpGateway:
    def complete(self, system: str, user: str) -> str:
        s = get_settings()
        if not s.ai_gateway_url:
            raise GatewayError("AI_GATEWAY_URL is not set")
        payload: dict[str, object] = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        if s.ai_gateway_model:
            payload["model"] = s.ai_gateway_model
        headers = {"Authorization": f"Bearer {s.ai_gateway_key.get_secret_value()}"}
        try:
            r = httpx.post(s.ai_gateway_url, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            # Type only: the exception text could echo the request.
            raise GatewayError(type(exc).__name__) from None
        if not isinstance(content, str):
            raise GatewayError("unusable reply")
        return content


def get_gateway() -> Gateway:
    """FastAPI dependency. Tests override it with recorded replies."""
    return HttpGateway()
