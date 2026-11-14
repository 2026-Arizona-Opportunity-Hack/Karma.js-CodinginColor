"""Typed errors mapped centrally to HTTP status codes (ENGINEERING 5)."""

from fastapi import FastAPI, Request
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


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
