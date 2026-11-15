"""/fields and custom values on donors and gifts (CUS-1 to CUS-4, D-141, D-146)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.clock import FixedClock, SystemClock, set_clock
from app.main import create_app
from tests import seed

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> Iterator[FixedClock]:
    c = FixedClock(T0)
    set_clock(c)
    yield c
    set_clock(SystemClock())


@pytest.fixture
def w(db: Session, clock: FixedClock) -> dict[str, int]:
    sam, ana = seed.add_user(db, "Sam"), seed.add_user(db, "Ana")
    donor = seed.add_donor(db, "Dee Donor", owner=sam)
    db.commit()
    return dict(sam=sam, ana=ana, donor=donor)


def login(name: str) -> TestClient:
    c = TestClient(create_app(), client=("203.0.113.5", 50000))
    r = c.post(
        "/api/app/auth/login", json={"email": f"{name}@example.org", "password": seed.PASSWORD}
    )
    assert r.status_code == 200
    return c


def send(c: TestClient, method: str, path: str, body: dict | None = None):
    return c.request(
        method, f"/api/app{path}", json=body, headers={"X-CSRF-Token": c.cookies.get("cic_csrf")}
    )


def new_field(c: TestClient, label: str, type_: str = "text", **kw) -> dict:
    r = send(c, "POST", "/fields", {"entity": "donor", "label": label, "type": type_, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def audited(db: Session, action: str) -> int:
    q = text("SELECT count(*) FROM audit_log WHERE action = :a")
    return db.execute(q, {"a": action}).scalar_one()


def test_fields_crud_lists_built_ins_and_keeps_order(db: Session, w) -> None:
    sam = login("sam")
    made = new_field(sam, "Giving Tier", "choice", choices=["Gold", "Silver"])
    assert (made["key"], made["is_builtin"], made["is_active"]) == ("giving_tier", False, True)
    assert (
        send(
            sam, "POST", "/fields", {"entity": "donor", "label": "giving tier", "type": "text"}
        ).status_code
        == 409
    )
    items = sam.get("/api/app/fields", params={"entity": "donor"}).json()["items"]
    assert [i["key"] for i in items][-2:] == ["kind", "giving_tier"]
    r = send(
        sam, "PATCH", f"/fields/{made['id']}", {"label": "Tier", "position": 5, "choices": ["Gold"]}
    )
    assert r.status_code == 200 and (r.json()["label"], r.json()["position"]) == ("Tier", 5)
    assert (
        send(
            sam, "POST", "/fields", {"entity": "donor", "label": "Bad", "type": "choice"}
        ).status_code
        == 422
    )
    assert audited(db, "field.create") == 1 and audited(db, "field.update") == 1


def test_managing_fields_follows_governance(db: Session, w) -> None:
    db.execute(
        text("UPDATE governance SET super_admin_user_id = :u, super_admin_state = 'active'"),
        {"u": w["ana"]},
    )
    db.commit()
    body = {"entity": "donor", "label": "Region", "type": "text"}
    assert send(login("sam"), "POST", "/fields", body).status_code == 403
    assert send(login("ana"), "POST", "/fields", body).status_code == 201
    assert (
        login("sam").get("/api/app/fields", params={"entity": "gift"}).status_code == 200
    )  # reading is open


def test_built_ins_can_be_relabeled_and_hidden_but_not_removed_or_retyped(db: Session, w) -> None:
    sam = login("sam")
    items = {
        i["key"]: i for i in sam.get("/api/app/fields", params={"entity": "donor"}).json()["items"]
    }
    gifts = {
        i["key"]: i for i in sam.get("/api/app/fields", params={"entity": "gift"}).json()["items"]
    }
    notes, email, kind = items["notes"], items["email"], items["kind"]
    assert send(sam, "DELETE", f"/fields/{notes['id']}").status_code == 409
    assert send(sam, "PATCH", f"/fields/{email['id']}", {"is_active": False}).status_code == 409
    assert (
        send(sam, "PATCH", f"/fields/{gifts['amount']['id']}", {"is_active": False}).status_code
        == 409
    )
    assert send(sam, "PATCH", f"/fields/{kind['id']}", {"choices": ["x"]}).status_code == 409
    assert send(sam, "PATCH", f"/fields/{notes['id']}", {"is_required": True}).status_code == 409
    r = send(
        sam,
        "PATCH",
        f"/fields/{notes['id']}",
        {"label": "Background", "type": "number", "key": "x"},
    )
    assert (r.json()["label"], r.json()["type"], r.json()["key"]) == (
        "Background",
        "long_text",
        "notes",
    )
    assert (
        send(sam, "PATCH", f"/fields/{notes['id']}", {"is_active": False}).json()["is_active"]
        is False
    )


def test_custom_values_are_validated_merged_and_returned_with_field_metadata(
    db: Session, w
) -> None:
    sam = login("sam")
    new_field(sam, "Giving Tier", "choice", choices=["Gold", "Silver"])
    new_field(sam, "Pledge", "money")
    path = f"/donors/{w['donor']}"
    bad = send(sam, "PATCH", path, {"custom": {"giving_tier": "Bronze"}})
    assert bad.status_code == 422 and bad.json()["error"]["message"].startswith("Giving Tier:")
    assert send(sam, "PATCH", path, {"custom": {"giving_tier": "Gold"}}).status_code == 200
    r = send(sam, "PATCH", path, {"custom": {"pledge": "$1,500"}})
    assert r.json()["custom"] == {"giving_tier": "Gold", "pledge": 150000}
    assert {"key": "pledge", "label": "Pledge", "type": "money"}.items() <= next(
        f for f in r.json()["fields"] if f["key"] == "pledge"
    ).items()
    cleared = send(sam, "PATCH", path, {"custom": {"giving_tier": None}}).json()
    assert cleared["custom"] == {"pledge": 150000}
    made = send(
        sam, "POST", "/donors", {"kind": "person", "display_name": "Zed", "custom": {"pledge": 5}}
    )
    assert made.status_code == 201 and made.json()["custom"] == {"pledge": 5}
    assert audited(db, "donor.update") == 3
    keys = (
        db.execute(
            text(
                "SELECT data->'custom_keys' FROM audit_log WHERE action='donor.update' ORDER BY id"
            )
        )
        .scalars()
        .all()
    )
    assert keys[0] == ["giving_tier"] and "Gold" not in str(keys)  # keys only, never values


def test_deactivate_keeps_values_restore_brings_them_back_and_delete_needs_an_unused_field(
    db: Session, w
) -> None:
    sam = login("sam")
    used, unused = new_field(sam, "Region"), new_field(sam, "Spare")
    path = f"/donors/{w['donor']}"
    send(sam, "PATCH", path, {"custom": {"region": "West"}})
    assert send(sam, "PATCH", f"/fields/{used['id']}", {"is_active": False}).status_code == 200
    hidden = sam.get(f"/api/app{path}").json()
    assert hidden["custom"] == {} and "region" not in [f["key"] for f in hidden["fields"]]
    assert db.execute(
        text("SELECT custom FROM donors WHERE id=:i"), {"i": w["donor"]}
    ).scalar_one() == {"region": "West"}
    assert (
        send(sam, "PATCH", path, {"custom": {"region": "East"}}).status_code == 422
    )  # deactivated
    assert send(sam, "DELETE", f"/fields/{used['id']}").status_code == 409
    assert send(sam, "PATCH", f"/fields/{used['id']}", {"is_active": True}).status_code == 200
    assert sam.get(f"/api/app{path}").json()["custom"] == {"region": "West"}
    assert send(sam, "DELETE", f"/fields/{unused['id']}").status_code == 204
    assert [audited(db, a) for a in ("field.deactivate", "field.restore", "field.delete")] == [
        1,
        1,
        1,
    ]


def test_contact_fields_are_hidden_from_everyone_but_the_owner(db: Session, w) -> None:
    sam = login("sam")
    new_field(sam, "Home Phone", is_contact=True)
    new_field(sam, "Region")
    send(
        sam,
        "PATCH",
        f"/donors/{w['donor']}",
        {"custom": {"home_phone": "555-0100", "region": "West"}},
    )
    assert sam.get(f"/api/app/donors/{w['donor']}").json()["custom"] == {
        "home_phone": "555-0100",
        "region": "West",
    }
    other = login("ana").get(f"/api/app/donors/{w['donor']}").json()
    assert other["custom"] == {"region": "West"}
    listed = login("ana").get("/api/app/donors", params={"scope": "all"}).json()["items"][0]
    assert listed["custom"] == {"region": "West"}


def test_gifts_take_custom_values_too(db: Session, w) -> None:
    sam = login("sam")
    r = send(sam, "POST", "/fields", {"entity": "gift", "label": "Check Number", "type": "number"})
    assert r.status_code == 201
    path = f"/donors/{w['donor']}/gifts"
    body = {"gift_date": "2026-11-01", "gross_cents": 5000}
    assert send(sam, "POST", path, {**body, "custom": {"check_number": "abc"}}).status_code == 422
    ok = send(sam, "POST", path, {**body, "custom": {"check_number": "1042"}})
    assert ok.status_code == 201 and ok.json()["custom"] == {"check_number": 1042}
    recent = sam.get(f"/api/app/donors/{w['donor']}").json()["recent_gifts"][0]
    assert recent["custom"] == {"check_number": 1042}


def test_the_public_api_never_returns_custom_values(db: Session, w) -> None:
    sam = login("sam")
    new_field(sam, "Secret Tier")
    send(sam, "PATCH", f"/donors/{w['donor']}", {"custom": {"secret_tier": "Platinum-Zed"}})
    seed.add_gift(db, w["donor"], date(2026, 11, 2), 2_500)
    db.execute(text('UPDATE gifts SET custom = \'{"secret_tier": "Platinum-Zed"}\'::jsonb'))
    db.commit()
    c = TestClient(
        create_app(), headers={"Authorization": f"Bearer {seed.add_api_key(db, w['sam'])}"}
    )
    db.commit()
    for path in ("summary", "totals/by-program", "totals/by-board-member", "activity/recent"):
        r = c.get(f"/api/v1/{path}")
        assert r.status_code == 200 and "Platinum-Zed" not in r.text and "custom" not in r.text
