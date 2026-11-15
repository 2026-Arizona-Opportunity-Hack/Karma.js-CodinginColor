"""NFR-1: security headers on every response, a strict CSP, and per-IP rate limits."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.middleware import SecurityMiddleware


def limited_app(*, login: int, general: int) -> TestClient:
    small = FastAPI()
    small.add_middleware(SecurityMiddleware, login_limit=login, app_limit=general)

    @small.post("/api/app/auth/login")
    def login_route() -> dict[str, str]:
        return {"ok": "yes"}

    @small.get("/api/app/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    @small.get("/healthz")
    def health() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(small)


def test_every_response_carries_the_security_headers_and_a_strict_csp() -> None:
    for path in ("/healthz", "/api/app/auth/me", "/nope"):
        h = TestClient(app).get(path).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert "max-age=31536000" in h["strict-transport-security"]
        csp = h["content-security-policy"]
        assert "frame-ancestors 'none'" in csp and "default-src 'self'" in csp
        assert "unsafe-inline'" not in csp.split("style-src-attr")[0]  # no inline scripts or styles
        assert "cdn.jsdelivr.net" not in csp


def test_only_the_api_docs_page_may_load_the_swagger_viewer_from_jsdelivr() -> None:
    docs = TestClient(app).get("/api/docs").headers["content-security-policy"]
    assert "https://cdn.jsdelivr.net" in docs and "frame-ancestors 'none'" in docs


def test_login_is_limited_per_ip_with_retry_after_and_the_error_shape() -> None:
    c = limited_app(login=2, general=100)
    assert [c.post("/api/app/auth/login").status_code for _ in range(2)] == [200, 200]
    r = c.post("/api/app/auth/login")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "too_many_requests"
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert r.headers["x-content-type-options"] == "nosniff"  # headers on the 429 too
    assert c.get("/api/app/ping").status_code == 200  # other routes use the general bucket


def test_the_general_app_limit_applies_but_health_and_static_paths_are_exempt() -> None:
    c = limited_app(login=100, general=3)
    assert [c.get("/api/app/ping").status_code for _ in range(4)] == [200, 200, 200, 429]
    assert all(c.get("/healthz").status_code == 200 for _ in range(10))
