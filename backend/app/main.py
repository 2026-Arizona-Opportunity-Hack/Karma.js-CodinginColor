"""App factory: routers, error handlers, and the built SPA."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.errors import NotFound, register_error_handlers
from app.openapi import install as install_openapi
from app.routes import (
    app_auth,
    app_donors,
    app_imports,
    app_members,
    app_messages,
    app_ownership,
    app_reports,
    app_settings,
    v1,
)
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CIC Compass",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    register_error_handlers(app)
    install_openapi(app)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(app_auth.router)
    app.include_router(v1.router)  # public read API, API-key auth (docs/API.md section 1)
    # Contract stubs (docs/API.md section 3): real schemas, 501 until each lane builds them.
    app.include_router(app_members.public_router)
    for module in (
        app_members,
        app_imports,
        app_donors,
        app_messages,
        app_ownership,
        app_reports,
        app_settings,
    ):
        app.include_router(module.router)

    _mount_spa(app, Path(settings.static_dir))
    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve frontend/dist when it exists; unknown non-API paths get index.html."""
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise NotFound()
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
