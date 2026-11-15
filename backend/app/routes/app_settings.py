"""Settings, templates, programs, program map, outcomes, API keys and demo reset.

In flat mode any member may change these; while a super admin is active only they may (GOV-4).
Lane C owns templates and API keys; lane A owns settings, programs, the map and outcomes.
"""

from fastapi import Response

from app.routes.stubs import session_router, todo
from app.schemas.settings import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyListOut,
    ApiKeyOut,
    OutcomeIn,
    OutcomeListOut,
    OutcomeOut,
    ProgramCreate,
    ProgramListOut,
    ProgramMapEntry,
    ProgramMapIn,
    ProgramMapListOut,
    ProgramOut,
    ProgramUpdate,
    SettingsIn,
    SettingsOut,
    TemplateIn,
    TemplateListOut,
    TemplateOut,
)

router = session_router("settings")


@router.get("/settings")
def get_settings() -> SettingsOut:
    todo("lane A, phase 4")


@router.put("/settings")
def put_settings(body: SettingsIn) -> SettingsOut:
    todo("lane A, phase 4")


@router.get("/templates")
def list_templates() -> TemplateListOut:
    todo("lane C, phase 3")


@router.put("/templates")
def put_template(body: TemplateIn) -> TemplateOut:
    """Create or replace the template for a kind and channel (MSG-1)."""
    todo("lane C, phase 3")


@router.get("/programs")
def list_programs() -> ProgramListOut:
    todo("lane A, phase 2")


@router.post("/programs", status_code=201)
def create_program(body: ProgramCreate) -> ProgramOut:
    todo("lane A, phase 4")


@router.put("/programs/{program_id}")
def update_program(program_id: int, body: ProgramUpdate) -> ProgramOut:
    todo("lane A, phase 4")


@router.get("/program-map")
def list_program_map() -> ProgramMapListOut:
    todo("lane A, phase 2")


@router.post("/program-map", status_code=201)
def create_program_map(body: ProgramMapIn) -> ProgramMapEntry:
    todo("lane A, phase 4")


@router.put("/program-map/{entry_id}")
def update_program_map(entry_id: int, body: ProgramMapIn) -> ProgramMapEntry:
    todo("lane A, phase 4")


@router.get("/program-outcomes")
def list_outcomes() -> OutcomeListOut:
    todo("lane A, phase 4")


@router.post("/program-outcomes", status_code=201)
def create_outcome(body: OutcomeIn) -> OutcomeOut:
    todo("lane A, phase 4")


@router.get("/api-keys")
def list_api_keys() -> ApiKeyListOut:
    todo("lane C, phase 2")


@router.post("/api-keys", status_code=201)
def create_api_key(body: ApiKeyCreate) -> ApiKeyCreated:
    """The full key is in this response only; afterwards just its prefix (API-1)."""
    todo("lane C, phase 2")


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int) -> ApiKeyOut:
    todo("lane C, phase 2")


@router.post("/demo/reset", status_code=204)
def demo_reset() -> Response:
    """Refused unless DEMO_MODE=true (NFR-9)."""
    todo("lane C, phase 4")
