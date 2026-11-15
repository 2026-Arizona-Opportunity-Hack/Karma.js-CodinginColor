"""Commit and reverse in the single request transaction owned by get_db.

No intermediate commits: gifts, donors, assignments and audits roll back together.
The advisory transaction lock serializes assignment and identity revalidation.
"""

from collections import Counter
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.clock import Clock
from app.db.models import Donor
from app.errors import Conflict, NotFound
from app.repos import dedupe, imports, ownership
from app.schemas.imports import ImportBatchOut, ImportListOut
from app.services.dedupe.resolver import identity_keys
from app.services.ingest.adapters import IncomingDonor
from app.services.ingest.preview import PreviewState, build_preview, previews
from app.services.ownership.assignment import assign_new


def list_batches(db: Session, actor: Actor) -> ImportListOut:
    return ImportListOut(
        items=[
            ImportBatchOut(**imports.batch_output(db, actor, batch))
            for batch in imports.list_batches(db, actor)
        ]
    )


def get(db: Session, actor: Actor, clock: Clock, batch_id: int) -> ImportBatchOut:
    batch = imports.find_batch(db, actor, batch_id)
    if batch:
        return ImportBatchOut(**imports.batch_output(db, actor, batch))
    return previews.get(batch_id, clock).output.batch


def _persist(
    db: Session, actor: Actor, clock: Clock, state: PreviewState, previous: dict[int, IncomingDonor]
) -> ImportBatchOut:
    batch = imports.save_batch(db, actor, state, clock.now())
    donors: dict[int, Donor] = {}
    profiles = {
        row.donor_token: row.incoming.donor
        for row in reversed(state.rows)
        if row.donor_token is not None and row.donor_token < 0
    }
    first_dates = dict.fromkeys(profiles, date.max)
    for row in state.rows:
        token = row.donor_token
        if token is not None and token in profiles and row.gifts:
            first_dates[token] = min(first_dates[token], *(g.gift.gift_date for g in row.gifts))
    order = sorted(
        profiles, key=lambda key: (first_dates[key], profiles[key].display_name.casefold(), -key)
    )
    for token in order:
        donors[token] = dedupe.create_donor(
            db, actor, profiles[token], clock.now(), action="import.run"
        )
        assign_new(db, actor, donors[token], clock)
    created_ids = [donor.id for donor in donors.values()]
    learned: set[tuple[int, str, str]] = set()

    def learn(donor: Donor, incoming: IncomingDonor) -> None:
        keys = {(donor.id, kind, value) for kind, value in identity_keys(incoming)}
        if not keys <= learned:
            dedupe.learn(
                db, actor, donor, incoming, batch.source, at=clock.now(), action="import.run"
            )
            learned.update(keys)

    inserted = 0
    for plan in state.rows:
        donor = None
        if plan.donor_token is not None:
            token = plan.donor_token
            if token not in donors:
                donors[token] = dedupe.active_donor(db, actor, token, action="import.run")
            donor = donors[token]
            if batch.source == "spreadsheet" and token in previous:
                learn(donor, previous[token])  # preserve the old primary contact as an identity
            learn(donor, plan.incoming.donor)
            if batch.source == "spreadsheet":
                imports.update_profile(db, actor, donor, plan.incoming.donor, clock.now())
        gifts = imports.save_gifts(db, actor, batch, plan, donor.id if donor else None, clock.now())
        inserted += len(gifts)
        saved_row = imports.save_row(db, actor, batch, plan, donor.id if donor else None, gifts)
        if plan.status == "needs_review":
            candidates = [donors[c].id if c < 0 else c for c in plan.candidates]
            imports.save_review(db, actor, saved_row, plan, [gift.id for gift in gifts], candidates)
    disbursements = Counter(
        row.incoming.disbursement_id for row in state.rows if row.incoming.disbursement_id
    )
    imports.finish(
        db,
        actor,
        batch,
        created_ids=created_ids,
        inserted_gifts=inserted,
        disbursements=dict(disbursements),
        at=clock.now(),
    )
    return ImportBatchOut(**imports.batch_output(db, actor, batch))


def commit(db: Session, actor: Actor, clock: Clock, batch_id: int) -> ImportBatchOut:
    ownership.lock(db, actor)
    if imports.find_batch(db, actor, batch_id, lock=True):
        raise Conflict("This preview has already been committed.")
    cached = previews.get(batch_id, clock)
    if not cached.output.commit_allowed or not cached.output.summary.reconciles:
        raise Conflict("Preview totals do not reconcile. Upload the file again.")
    context = imports.snapshot(
        db, actor, cached.output.batch.source, b"", file_sha256=cached.file_sha256
    )
    state = build_preview(
        cached.output.batch.source,
        cached.output.batch.filename,
        b"",
        cached.source_rows,
        context,
        clock,
    )
    if not state.output.summary.reconciles:
        raise Conflict("Import totals do not reconcile.")
    state.file_sha256 = cached.file_sha256
    state.output.batch = cached.output.batch.model_copy(
        update={
            "summary": state.output.summary,
            "cutoff_date": state.output.batch.cutoff_date,
        }
    )
    try:
        return _persist(db, actor, clock, state, context.donors)
    except IntegrityError as exc:
        raise Conflict(
            "The import conflicted with another change. Preview the file again."
        ) from exc


def reverse(db: Session, actor: Actor, clock: Clock, batch_id: int) -> ImportBatchOut:
    ownership.lock(db, actor)
    batch = imports.find_batch(db, actor, batch_id, lock=True)
    if batch is None:
        raise NotFound("Import batch not found.")
    imports.reverse(db, actor, batch, clock.now())
    return ImportBatchOut(**imports.batch_output(db, actor, batch))
