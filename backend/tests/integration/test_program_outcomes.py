"""Program outcomes by hand (RPT-3, issue #40): list, create, denied, bad input, audit."""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import create_app
from tests import seed

BODY = {
    "period_start": "2026-01-01",
    "period_end": "2026-06-30",
    "metric_label": "Students served",
    "value": "120.5",
    "unit": "students",
    "source_note": "Spring report",
}


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def post(c: TestClient, body: dict):
    return c.post(
        "/api/app/program-outcomes", json=body, headers={"X-CSRF-Token": c.cookies["cic_csrf"]}
    )


def program(db: Session) -> int:
    return db.execute(
        text("INSERT INTO programs (name, slug) VALUES ('Robotics', 'robotics') RETURNING id")
    ).scalar_one()


def test_member_enters_an_outcome_and_it_lists_with_its_program(db: Session) -> None:
    seed.add_user(db, "Diana")
    pid = program(db)
    db.commit()
    c = login("diana")
    r = post(c, {**BODY, "program_id": pid})
    assert r.status_code == 201
    assert r.json()["program"]["name"] == "Robotics"
    items = c.get("/api/app/program-outcomes").json()["items"]
    assert [(i["metric_label"], i["unit"], float(i["value"])) for i in items] == [
        ("Students served", "students", 120.5)
    ]


def test_creating_an_outcome_writes_an_audit_entry(db: Session) -> None:
    seed.add_user(db, "Diana")
    pid = program(db)
    db.commit()
    post(login("diana"), {**BODY, "program_id": pid})
    n = db.execute(text("SELECT count(*) FROM audit_log WHERE action = 'outcome.create'"))
    assert n.scalar_one() == 1


def test_a_member_is_refused_while_a_super_admin_is_active(db: Session) -> None:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    pid = program(db)
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
             "WHERE id = 1"),
        {"u": diana},
    )  # fmt: skip
    db.commit()
    assert sam
    assert post(login("sam"), {**BODY, "program_id": pid}).status_code == 403
    assert post(login("diana"), {**BODY, "program_id": pid}).status_code == 201


def test_bad_input_is_refused(db: Session) -> None:
    seed.add_user(db, "Diana")
    pid = program(db)
    db.commit()
    c = login("diana")
    assert post(c, {**BODY, "program_id": 9999}).status_code == 400  # no such program
    backwards = {**BODY, "program_id": pid, "period_end": "2025-12-31"}
    assert post(c, backwards).status_code == 400
    assert post(c, {**BODY, "program_id": pid, "value": "lots"}).status_code in (400, 422)


# --- CSV upload (issue #135) -------------------------------------------------------------------
HEADER = "program,period_start,period_end,metric_label,value,unit,source_note\n"
GOOD = "Robotics,2026-01-01,2026-06-30,Students served,120,students,Spring\n"


def upload(c: TestClient, content: str | bytes, name: str = "outcomes.csv"):
    data = content.encode() if isinstance(content, str) else content
    return c.post(
        "/api/app/program-outcomes/upload",
        files={"file": (name, data, "text/csv")},
        headers={"X-CSRF-Token": c.cookies["cic_csrf"]},
    )


def count(db: Session) -> int:
    return db.execute(text("SELECT count(*) FROM program_outcomes")).scalar_one()


def test_upload_saves_every_row_and_audits_it(db: Session) -> None:
    seed.add_user(db, "Diana")
    program(db)
    db.commit()
    rows = GOOD + "robotics,2026-07-01,2026-12-31,Workshops,8,workshops,\n"
    r = upload(login("diana"), HEADER + rows)
    assert r.status_code == 201 and len(r.json()["items"]) == 2
    assert count(db) == 2
    audit = text("SELECT count(*) FROM audit_log WHERE action = 'outcome.upload'")
    assert db.execute(audit).scalar_one() == 1


def test_one_bad_row_rejects_the_whole_file_and_names_the_row(db: Session) -> None:
    seed.add_user(db, "Diana")
    program(db)
    db.commit()
    bad = GOOD + "Robotics,2026-07-01,2026-12-31,Workshops,lots,workshops,\n"
    bad += "Gardening,2026-07-01,2026-12-31,Beds,3,beds,\n"
    r = upload(login("diana"), HEADER + bad)
    assert r.status_code == 400
    assert "row 3" in r.json()["error"]["message"] and "row 4" in r.json()["error"]["message"]
    assert count(db) == 0


def test_upload_refuses_wrong_types_missing_columns_and_big_files(db: Session) -> None:
    seed.add_user(db, "Diana")
    program(db)
    db.commit()
    c = login("diana")
    assert upload(c, HEADER + GOOD, name="outcomes.xlsx").status_code == 415
    assert upload(c, b"%PDF-1.4 not a csv").status_code == 415
    assert upload(c, "program,unit\nRobotics,kids\n").status_code == 400
    assert upload(c, HEADER + GOOD + "x" * (1024 * 1024)).status_code == 413
    assert count(db) == 0


def test_upload_is_refused_for_a_member_while_a_super_admin_is_active(db: Session) -> None:
    diana, sam = seed.add_user(db, "Diana"), seed.add_user(db, "Sam")
    program(db)
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active' "
             "WHERE id = 1"),
        {"u": diana},
    )  # fmt: skip
    db.commit()
    assert sam
    assert upload(login("sam"), HEADER + GOOD).status_code == 403
    assert count(db) == 0
