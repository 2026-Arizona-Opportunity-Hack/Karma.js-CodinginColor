"""Settings, templates, programs, program map, outcomes, API keys and demo reset.

In flat mode any member may change these; while a super admin is active only they may (GOV-4).
Lane C owns templates and API keys; lane A owns settings, programs, the map and outcomes.
"""

from typing import Annotated

from fastapi import File, Response, UploadFile

from app.db.models import ApiKey
from app.repos import apikeys
from app.routes.deps import DB, ClockDep, CurrentDep
from app.routes.stubs import session_router, todo
from app.schemas.common import ErrorOut
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
from app.services.apikeys import service as apikey_service
from app.services.messaging import service as messaging
from app.services.reports import outcomes as outcome_service

router = session_router("settings")


@router.get("/settings")
def get_settings() -> SettingsOut:
    todo("lane A, phase 4")


@router.put("/settings")
def put_settings(body: SettingsIn) -> SettingsOut:
    todo("lane A, phase 4")


@router.get("/templates")
def list_templates(cur: CurrentDep, db: DB) -> TemplateListOut:
    return messaging.list_templates(db, cur.actor)


@router.put("/templates")
def put_template(body: TemplateIn, cur: CurrentDep, db: DB) -> TemplateOut:
    """Create or replace the template for a kind and channel (MSG-1)."""
    return messaging.put_template(db, cur.actor, body)


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
def list_outcomes(cur: CurrentDep, db: DB) -> OutcomeListOut:
    return outcome_service.list_outcomes(db, cur.actor)


@router.post(
    "/program-outcomes/upload",
    status_code=201,
    responses={
        413: {"model": ErrorOut, "description": "File over 1 MB"},
        415: {"model": ErrorOut, "description": "Not a CSV file"},
    },
)
def upload_outcomes(file: Annotated[UploadFile, File()], cur: CurrentDep, db: DB) -> OutcomeListOut:
    """CSV columns: program, period_start, period_end, metric_label, value, unit, source_note.
    Any bad row rejects the whole file and names the rows."""
    data = file.file.read(outcome_service.UPLOAD_MAX_BYTES + 1)
    return outcome_service.upload_outcomes(db, cur.actor, file.filename or "upload.csv", data)


@router.post("/program-outcomes", status_code=201)
def create_outcome(body: OutcomeIn, cur: CurrentDep, db: DB) -> OutcomeOut:
    return outcome_service.create_outcome(db, cur.actor, body)


def _key_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        scopes=list(row.scopes),
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


@router.get("/api-keys")
def list_api_keys(cur: CurrentDep, db: DB) -> ApiKeyListOut:
    return ApiKeyListOut(items=[_key_out(r) for r in apikeys.list_all(db, cur.actor)])


@router.post("/api-keys", status_code=201)
def create_api_key(body: ApiKeyCreate, cur: CurrentDep, db: DB) -> ApiKeyCreated:
    """The full key is in this response only; afterwards just its prefix (API-1)."""
    made = apikey_service.create(db, cur.actor, name=body.name, scopes=list(body.scopes))
    return ApiKeyCreated(**_key_out(made.row).model_dump(), key=made.key)


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int, cur: CurrentDep, db: DB, clock: ClockDep) -> ApiKeyOut:
    return _key_out(apikey_service.revoke(db, clock, cur.actor, key_id))


@router.post("/demo/reset", status_code=204)
def demo_reset() -> Response:
    """Refused unless DEMO_MODE=true (NFR-9)."""
    todo("lane C, phase 4")
