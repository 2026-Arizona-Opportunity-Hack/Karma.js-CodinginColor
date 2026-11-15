"""OpenAPI tweaks so the document matches behaviour (see docs/API.md section 3)."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def install(app: FastAPI) -> None:
    def build() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version="0.1.0", routes=app.routes)
        # Validation failures return 400 in our error shape, never FastAPI's default 422.
        for path in schema["paths"].values():
            for operation in path.values():
                operation.get("responses", {}).pop("422", None)
        for name in ("HTTPValidationError", "ValidationError"):
            schema.get("components", {}).get("schemas", {}).pop(name, None)
        app.openapi_schema = schema
        return schema

    app.openapi = build  # type: ignore[method-assign]
