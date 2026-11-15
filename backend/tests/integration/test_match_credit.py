"""D-127: employer money is org revenue, but never the employee's giving."""

from datetime import date

from sqlalchemy import text

from app.authz.actor import Actor
from app.repos import donors, reports
from app.services.reports import retention
from tests import seed


def test_match_is_org_revenue_but_not_employee_totals_or_retention(db):
    owner = seed.add_user(db, "Diana")
    actor = Actor(kind="user", id=owner)
    donor = seed.add_donor(db, "Ada Jones", owner=owner)
    seed.add_gift(db, donor, date(2025, 5, 1), 10000)
    seed.add_gift(db, donor, date(2026, 10, 1), 5000)
    match = seed.add_gift(db, donor, date(2026, 11, 14), 50000)
    db.execute(
        text("UPDATE gifts SET is_matching_gift = true, payer_name = 'Employer' WHERE id = :id"),
        {"id": match},
    )
    today = date(2026, 11, 15)
    card = donors.get_card(db, actor, donor, today=today)
    assert card["total_lifetime_cents"] == 15000
    assert card["total_12m_cents"] == 5000
    assert card["last_gift_date"] == date(2026, 10, 1)
    result = retention.build(db, actor, as_of=today, basis="rolling")
    assert result.classes["decreased"].donors == 1
    assert result.classes["decreased"].cents_cur == 5000
    assert result.classes["decreased"].cents_prev == 10000
    org = reports.totals(db, actor, start=date(2025, 1, 1), end=today)
    assert org["gross_cents"] == 65000 and org["gift_count"] == 3
    program = reports.by_program(db, actor, start=date(2025, 1, 1), end=today)
    assert program[0]["gross_cents"] == 65000
    board = reports.by_board_member(db, actor, start=date(2025, 1, 1), end=today)
    assert board[0]["gross_cents"] == 15000
    # Retain the relationship and labeled history; the match is not erased.
    history = donors.recent_gifts(db, actor, [donor])[donor]
    assert any(g["id"] == match and g["is_matching_gift"] for g in history)


def test_match_alone_does_not_make_an_employee_a_new_or_retained_donor(db):
    owner = seed.add_user(db, "Diana")
    actor = Actor(kind="user", id=owner)
    donor = seed.add_donor(db, "Ada Jones", owner=owner)
    match = seed.add_gift(db, donor, date(2026, 11, 14), 5000)
    db.execute(text("UPDATE gifts SET is_matching_gift = true WHERE id = :id"), {"id": match})
    today = date(2026, 11, 15)
    result = retention.build(db, actor, as_of=today, basis="rolling")
    assert all(bucket.donors == 0 for bucket in result.classes.values())
    org = reports.totals(db, actor, start=date(2026, 1, 1), end=today)
    assert org["gross_cents"] == 5000 and org["new_donors"] == 0
    assert org["donor_count"] == 0
