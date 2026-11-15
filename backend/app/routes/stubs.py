"""Helpers for contract stubs. A lane replaces `todo(...)` with real behaviour in its own file.

Stubs already enforce the session and CSRF (same dependency as real routes), so the frontend
sees the true auth behaviour and an honest 501 until the feature lands.
"""

from typing import NoReturn

from fastapi import APIRouter, Depends

from app.errors import NotImplementedYet
from app.routes.deps import current
from app.schemas.common import ErrorOut

ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorOut, "description": "Validation failed"},
    401: {"model": ErrorOut, "description": "No session"},
    403: {"model": ErrorOut, "description": "Policy denied or bad CSRF token"},
    404: {"model": ErrorOut, "description": "Not found or not visible"},
}


def session_router(tag: str) -> APIRouter:
    return APIRouter(
        prefix="/api/app",
        tags=[f"app:{tag}"],
        dependencies=[Depends(current)],
        responses=ERRORS,
    )


def todo(owner: str) -> NoReturn:
    raise NotImplementedYet(f"Not built yet ({owner}).")
