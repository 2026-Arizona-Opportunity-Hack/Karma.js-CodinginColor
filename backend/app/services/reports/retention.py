"""Retention classes (RPT-2, DATA_MODEL 3.5, D-114). Shared by /api/v1 and the app's Reports page.

Rolling basis, as of T: current = (T-365, T], previous = (T-730, T-365], and a donor "gave
before" if they have a gift on or before T-730. Calendar basis uses the calendar year of T and the
one before it. Only linked employee donations count (D-127); employer matches,
deleted and merged donors are left out."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal, get_args

from sqlalchemy.orm import Session

from app.authz.actor import Actor
from app.repos import reports as repo
from app.schemas.reports import RetentionClass, RetentionClassName, RetentionDonor, RetentionReport

Basis = Literal["rolling", "calendar"]
CLASS_NAMES: tuple[RetentionClassName, ...] = get_args(RetentionClassName)


def classify(cents_cur: int, cents_prev: int, ever_before: bool) -> RetentionClassName | None:
    """The class of one donor, or None when they gave in neither window."""
    if cents_cur > 0 and cents_prev == 0:
        return "reactivated" if ever_before else "new"
    if cents_cur > 0:
        if cents_cur > cents_prev:
            return "increased"
        return "same" if cents_cur == cents_prev else "decreased"
    return "lapsed" if cents_prev > 0 else None


def windows(as_of: date, basis: Basis) -> tuple[tuple[date, date], tuple[date, date], date]:
    """Inclusive (current, previous) date ranges and the day before which "gave before" looks."""
    if basis == "calendar":
        cur = (date(as_of.year, 1, 1), date(as_of.year, 12, 31))
        prev = (date(as_of.year - 1, 1, 1), date(as_of.year - 1, 12, 31))
        return cur, prev, prev[0]
    cur = (as_of - timedelta(days=364), as_of)  # (T-365, T]
    prev = (as_of - timedelta(days=729), as_of - timedelta(days=365))  # (T-730, T-365]
    return cur, prev, as_of - timedelta(days=729)  # on or before T-730


@dataclass
class Retention:
    as_of: date
    basis: Basis
    classes: dict[RetentionClassName, RetentionClass] = field(default_factory=dict)
    donors: dict[RetentionClassName, list[RetentionDonor]] = field(default_factory=dict)


def build(db: Session, actor: Actor, *, as_of: date, basis: Basis) -> Retention:
    cur, prev, before = windows(as_of, basis)
    result = Retention(as_of=as_of, basis=basis)
    for cls in CLASS_NAMES:
        result.classes[cls] = RetentionClass(donors=0, cents_cur=0, cents_prev=0)
        result.donors[cls] = []
    rows: list[dict[str, Any]] = repo.retention_donors(db, actor, cur=cur, prev=prev, before=before)
    for r in rows:
        name = classify(r["cents_cur"], r["cents_prev"], r["ever_before"])
        if name is None:
            continue
        bucket = result.classes[name]
        bucket.donors += 1
        bucket.cents_cur += r["cents_cur"]
        bucket.cents_prev += r["cents_prev"]
        result.donors[name].append(
            RetentionDonor(
                donor_id=r["donor_id"],
                display_name=r["display_name"],
                cents_cur=r["cents_cur"],
                cents_prev=r["cents_prev"],
            )
        )
    return result


def to_app_report(r: Retention) -> RetentionReport:
    return RetentionReport(as_of=r.as_of, basis=r.basis, classes=r.classes, donors=r.donors)
