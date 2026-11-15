# ruff: noqa: F811 (the fixtures come from tests.msgkit and are used as arguments)
"""The reminder digest (REM-6, D-109, acceptance test 10)."""

from datetime import date

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests import seed
from tests.integration.test_message_send import Net, ok
from tests.msgkit import clock, login, make_super_admin, post, w  # noqa: F401

DIANA = "diana.owner@example.org"
SAM = "sam.other@example.org"


def add_next_steps(db: Session, w) -> None:
    """Diana has 2 next steps due, Sam has 1."""
    seed.add_donor(db, "Extra Donor", owner=w["diana"])
    seed.add_next_step(db, w["zelda"], w["diana"], "Call", date(2026, 11, 16))
    d2 = db.execute(text("SELECT id FROM donors WHERE display_name = 'Extra Donor'")).scalar_one()
    seed.add_next_step(db, d2, w["diana"], "Visit", date(2026, 11, 17))
    seed.add_next_step(db, w["nia"], w["sam"], "Email", date(2026, 11, 16))
    db.commit()


def test_digest_dry_run_records_one_run_with_each_members_own_counts_only(db: Session, w) -> None:
    add_next_steps(db, w)
    net = Net()  # fails if used: dry_run makes no network call
    c = login(DIANA, net.overrides("dry_run"))
    r = post(c, "/digest/send")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "dry_run" and out["recipients"] == 2 and net.requests == []
    counts = {m["member"]["display_name"]: m["next_step_due"] for m in out["members"]}
    assert counts == {"Diana Owner": 2, "Sam Other": 1}
    run = db.execute(text("SELECT mode, recipients, details::text AS d FROM digest_runs")).one()
    assert run.mode == "dry_run" and run.recipients == 2
    assert "Zelda" not in run.d and "Nia" not in run.d  # counts only, no donor names
    assert (
        db.execute(text("SELECT count(*) FROM audit_log WHERE action='digest.send'")).scalar_one()
        == 1
    )


def test_live_digest_emails_members_only_with_counts(db: Session, w) -> None:
    add_next_steps(db, w)
    net = Net(ok)
    c = login(DIANA, net.overrides("live"))
    assert post(c, "/digest/send").status_code == 200
    sent = [httpx.Response(200, content=r.content).json() for r in net.requests]
    assert sorted(s["to"][0] for s in sent) == [DIANA, SAM]
    assert all("Zelda" not in s["text"] and "Nia" not in s["text"] for s in sent)


def test_digest_follows_governance_and_needs_a_session(db: Session, w) -> None:
    make_super_admin(db, w["sam"])
    assert post(login(DIANA, Net().overrides("dry_run")), "/digest/send").status_code == 403
    assert post(login(SAM, Net().overrides("dry_run")), "/digest/send").status_code == 200
    assert db.execute(text("SELECT count(*) FROM digest_runs")).scalar_one() == 1
