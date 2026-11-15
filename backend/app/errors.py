"""Typed errors mapped centrally to HTTP status codes (ENGINEERING 5)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status = 500
    code = "error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message or self.code.replace("_", " ")


class Invalid(AppError):
    status, code = 400, "invalid"


class Unauthorized(AppError):
    status, code = 401, "unauthorized"


class Forbidden(AppError):
    status, code = 403, "forbidden"


class NotFound(AppError):
    status, code = 404, "not_found"


class Conflict(AppError):
    status, code = 409, "conflict"


class TooManyRequests(AppError):
    status, code = 429, "too_many_requests"


class NotImplementedYet(AppError):
    """Contract stub: the route and its schemas exist, the behaviour lands in a later phase."""

    status, code = 501, "not_implemented"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        """API.md: 400 for validation, in the same error shape as every other error."""
        first = exc.errors()[:3]
        parts = [
            f"{'.'.join(str(p) for p in e['loc'][1:]) or e['loc'][0]}: {e['msg']}" for e in first
        ]
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid", "message": "; ".join(parts)}},
        )
