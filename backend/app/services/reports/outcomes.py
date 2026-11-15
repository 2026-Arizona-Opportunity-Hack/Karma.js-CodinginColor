"""Program outcomes entered by hand (RPT-3)."""

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.db.models import Program, ProgramOutcome
from app.repos import audit, outcomes
from app.schemas.settings import OutcomeIn, OutcomeListOut, OutcomeOut, ProgramOut


def to_out(o: ProgramOutcome, p: Program) -> OutcomeOut:
    return OutcomeOut(
        id=o.id,
        program=ProgramOut(id=p.id, name=p.name, slug=p.slug, is_active=p.is_active),
        period_start=o.period_start,
        period_end=o.period_end,
        metric_label=o.metric_label,
        value=o.value,
        unit=o.unit,
        source_note=o.source_note,
    )


def list_outcomes(db: Session, actor: Actor) -> OutcomeListOut:
    return OutcomeListOut(items=[to_out(o, p) for o, p in outcomes.list_all(db, actor)])


def create_outcome(db: Session, actor: Actor, body: OutcomeIn) -> OutcomeOut:
    row, program = outcomes.create(db, actor, **body.model_dump())
    audit.write(
        db, actor, "outcome.create", entity="program_outcome", entity_id=row.id,
        data={"program_id": program.id, "metric_label": row.metric_label},
    )  # fmt: skip
    return to_out(row, program)
