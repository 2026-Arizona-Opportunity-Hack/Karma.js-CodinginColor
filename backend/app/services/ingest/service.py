"""Coordinate upload preview; all SQL remains in the import repository."""

from pathlib import PurePath

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.repos import imports as repo
from app.schemas.common import ImportSource
from app.schemas.imports import ImportPreviewOut
from app.services.fields import service as fields
from app.services.ingest.adapters import parse_upload_with_columns
from app.services.ingest.preview import build_preview, previews


def preview(
    db: Session,
    actor: Actor,
    clock: Clock,
    source: ImportSource,
    filename: str,
    data: bytes,
) -> ImportPreviewOut:
    repo.require(actor)
    defs = fields.definitions(db, "donor") + fields.definitions(db, "gift")
    rows, ignored = parse_upload_with_columns(source, filename, data, defs)
    current = repo.snapshot(db, actor, source, data)
    state = build_preview(source, PurePath(filename).name, data, rows, current, clock)
    state.output.ignored_columns = ignored
    previews.put(state, clock)
    return state.output
