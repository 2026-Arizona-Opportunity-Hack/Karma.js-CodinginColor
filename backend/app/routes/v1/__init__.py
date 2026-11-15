"""Public read API, `/api/v1` (docs/API.md section 1). API-key auth, aggregates only (D-113)."""

from fastapi import APIRouter

from app.routes.v1 import aggregates, health

router = APIRouter()
router.include_router(health.router)
router.include_router(aggregates.router)
