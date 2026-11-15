"""Independent check of fixtures/manifest.json.

Everything here is recomputed from the fixture FILES ALONE with its own parsers, identity
resolver and retention code, written from DATA_MODEL 3.1, 3.2, 3.5 and SRS DED-3, not from
fixtures/generate.py. If the generator's designed outcomes and these rules disagree, a test
fails. Doubles as a first executable statement of the matching rules for lane A.
"""

import csv
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import pytest
from openpyxl import load_workbook

FIX = Path(__file__).resolve().parents[3] / "fixtures"
M = json.loads((FIX / "manifest.json").read_text(encoding="utf-8"))
SHEET, ZEFFY, BENEVITY, GENERIC = M["import_order"]


# ------------------------------------------------------------------ parsing (DATA_MODEL 3.2)


def read_rows(name: str) -> list[dict[str, str]]:
    path = FIX / name
    if path.suffix == ".xlsx":
        ws = load_workbook(path, read_only=True).worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = [str(h) for h in next(it)]
        return [
            {h: ("" if v is None else str(v)) for h, v in zip(head, r, strict=True)} for r in it
        ]
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_date(text: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_cents(text: str) -> tuple[int | None, str | None]:
    """(cents, None) or (None, reason). Negative and zero are rejected for gifts."""
    t = text.strip().replace("$", "").replace(",", "")
    if not t:
        return None, "bad_amount"
    negative = t.startswith("(") and t.endswith(")")
    try:
        value = Decimal(t.strip("()"))
    except InvalidOperation:
        return None, "bad_amount"
    cents = int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if negative or cents <= 0:
        return None, "non_positive_amount"
    return cents, None


def norm_email(v: str) -> str:
    return v.strip().lower()


def norm_phone(v: str) -> str:
    d = re.sub(r"\D", "", v)
    if len(d) == 10:
        return "+1" + d
    if len(d) == 11 and d.startswith("1"):
        return "+" + d
    return d


def norm_name(v: str) -> str:
    v = unicodedata.normalize("NFKC", v).lower()
    v = re.sub(r"[^\w\s]", " ", v)
    return " ".join(w for w in v.split() if w not in {"mr", "mrs", "ms", "dr"})


# ------------------------------------------------------------------ one record per row


def split_name(full: str) -> tuple[str, str | None]:
    parts = full.split()
    return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (full, None)


def record(source: str, r: dict[str, str]) -> dict:
    """Normalized identity fields for a row (anonymous rows get name/email None)."""
    if source == "sheet":
        person = r["Type"] == "Individual"
        first, last = (r["First name"], r["Last name"]) if person else (r["Name"], None)
        return dict(name=r["Name"], first=first, last=last or None, email=r["Email"],
                    phone=r["Phone"], employer=r["Organization"] if person else "",
                    zid="", bid="", anon=False)  # fmt: skip
    if source == "zeffy":
        full = f"{r['First name']} {r['Last name']}".strip()
        return dict(name=full, first=r["First name"], last=r["Last name"] or None,
                    email=r["Email"], phone=r["Phone"], employer="", zid=r["Contact ID"],
                    bid="", anon=not (full or r["Email"]))  # fmt: skip
    if source == "benevity":
        full = f"{r['Donor First Name']} {r['Donor Last Name']}".strip()
        company = r["Company Name"]
        # A code such as A1234 instead of a name means the company asked to stay anonymous.
        employer = "" if re.fullmatch(r"[A-Z]\d{4}", company) else company
        return dict(name=full, first=r["Donor First Name"], last=r["Donor Last Name"] or None,
                    email=r["Donor Email"], phone="", employer=employer, zid="", bid="",
                    anon=not (full or r["Donor Email"]))  # fmt: skip
    first, last = split_name(r["Donor name"])
    return dict(name=r["Donor name"], first=first, last=last, email=r["Email"], phone=r["Phone"],
                employer=r["Organization"], zid="", bid="",
                anon=not (r["Donor name"] or r["Email"]))  # fmt: skip


def validate(source: str, r: dict[str, str]) -> tuple[str | None, date | None, int]:
    """(invalid code or None, gift date, cents)."""
    if source == "zeffy":
        if r["Payment status"].lower() != "succeeded":
            return "not_succeeded", None, 0
        if r["Currency"].upper() != "USD":
            return "non_usd", None, 0
        if Decimal(r["Refunded amount"] or "0") > 0:
            return "refunded", None, 0
    if source == "benevity" and r["Donation Currency"].upper() != "USD":
        return "non_usd", None, 0
    when = parse_date(r["Date"] if source in ("zeffy", "generic") else r["Donation Date"])
    if when is None:
        return "bad_date", None, 0
    cents, why = parse_cents(r["Donation Amount" if source == "benevity" else "Amount"])
    return (why, None, 0) if why else (None, when, cents)  # type: ignore[return-value]


# ------------------------------------------------------------------ identity resolution (DED-3)


def conflict(a: dict, b: dict) -> bool:
    if a["last"] and b["last"] and norm_name(a["last"]) != norm_name(b["last"]):
        return True
    fa, fb = norm_name(a["first"] or ""), norm_name(b["first"] or "")
    return bool(fa and fb and fa[0] != fb[0])


class Resolver:
    def __init__(self) -> None:
        self.donors: list[dict] = []
        self.idx: dict[tuple[str, str], int] = {}

    def keys(self, rec: dict) -> list[tuple[str, str]]:
        k = []
        if rec["email"]:
            k.append(("email", norm_email(rec["email"])))
        if rec["phone"]:
            k.append(("phone", norm_phone(rec["phone"])))
        if rec["zid"]:
            k.append(("zeffy", rec["zid"]))
        if rec["bid"]:
            k.append(("benevity", rec["bid"]))
        if rec["employer"] and rec["name"]:
            k.append(("name_org", norm_name(rec["name"]) + "|" + norm_name(rec["employer"])))
        return k

    def decide(self, rec: dict) -> tuple[str, int | None, str | None]:
        look = lambda *k: self.idx.get(k)  # noqa: E731
        for kind, val in self.keys(rec):
            if kind in ("zeffy", "benevity") and (d := look(kind, val)) is not None:
                return "link", d, None  # platform id already known
        if rec["email"] and (d := look("email", norm_email(rec["email"]))) is not None:
            if conflict(rec, self.donors[d]):
                return "review", d, "name_conflict"
            return "link", d, None
        if rec["phone"] and look("phone", norm_phone(rec["phone"])) is not None:
            return "review", None, "phone"
        for kind, val in self.keys(rec):
            if kind == "name_org" and look(kind, val) is not None:
                return "review", None, "name_employer"
        return "new", None, None  # never by name alone

    def learn(self, did: int, rec: dict) -> None:
        for k in self.keys(rec):
            self.idx.setdefault(k, did)

    def create(self, rec: dict) -> int:
        self.donors.append(rec)
        did = len(self.donors) - 1
        self.learn(did, rec)
        return did


def add_attribution(f: dict, attribution: str, cents: int, match: int) -> None:
    bucket = f["attr"][attribution]
    bucket["gifts"] += 1 + (match > 0)
    bucket["cents"] += cents + match
    bucket["rows"] += 1
    bucket["donation_cents"] += cents
    bucket["match_cents"] += match


def run_imports() -> dict:
    res, out = Resolver(), {"files": {}, "review": [], "gifts": {}}
    for source, name in zip(
        ["sheet", "zeffy", "benevity", "generic"], M["import_order"], strict=True
    ):
        f = {"rows": 0, "invalid": [], "created": 0, "gifts": 0, "cents": 0,
             "attr": {k: {"gifts": 0, "cents": 0, "rows": 0,
                          "donation_cents": 0, "match_cents": 0}
                      for k in ("linked", "pending_review", "anonymous")}}  # fmt: skip
        for n, r in enumerate(read_rows(name), start=1):
            f["rows"] += 1
            if source == "sheet":
                code, when, cents = None, None, 0
            else:
                code, when, cents = validate(source, r)
            if code:
                f["invalid"].append({"row": n, "code": code})
                continue
            rec = record(source, r)
            match = 0
            if source == "benevity" and r["Match Amount"].strip():
                match = int((Decimal(r["Match Amount"]) * 100).quantize(Decimal(1)))
            n_gifts = 1 + (match > 0)
            if rec["anon"]:
                f["gifts"] += n_gifts
                f["cents"] += cents + match
                add_attribution(f, "anonymous", cents, match)
                continue
            verdict, did, why = res.decide(rec)
            if verdict == "review":
                if source == "sheet" and why == "name_conflict":
                    why = "household"
                out["review"].append({"file": name, "row": n, "reason": why})
                if source != "sheet":
                    f["gifts"] += n_gifts
                    f["cents"] += cents + match
                    add_attribution(f, "pending_review", cents, match)
                continue
            if verdict == "new":
                did = res.create(rec)
                f["created"] += 1
            else:
                assert did is not None
                res.learn(did, rec)
            if source != "sheet":
                f["gifts"] += n_gifts
                f["cents"] += cents + match
                add_attribution(f, "linked", cents, match)
                out["gifts"].setdefault(did, []).append((when, cents))
                # D-127: matches stay in org revenue above, not donor retention gifts.
        out["files"][name] = f
    out["donors"] = len(res.donors)
    return out


# ------------------------------------------------------------------ retention (DATA_MODEL 3.5)


def retention(gifts: dict[int, list[tuple[date, int]]], as_of: date) -> dict[str, dict[str, int]]:
    cur_from, prev_from = as_of - timedelta(days=365), as_of - timedelta(days=730)
    out = {c: {"donors": 0, "cents_cur": 0, "cents_prev": 0}
           for c in ("new", "reactivated", "increased", "same", "decreased", "lapsed")}  # fmt: skip
    for items in gifts.values():
        cur = sum(c for d, c in items if cur_from < d <= as_of)
        prev = sum(c for d, c in items if prev_from < d <= cur_from)
        ever_before = any(d <= prev_from for d, _ in items)
        if cur and not prev:
            cls = "reactivated" if ever_before else "new"
        elif cur and prev:
            cls = "increased" if cur > prev else "decreased" if cur < prev else "same"
        elif prev:
            cls = "lapsed"
        else:
            continue
        out[cls]["donors"] += 1
        out[cls]["cents_cur"] += cur
        out[cls]["cents_prev"] += prev
    return out


# ------------------------------------------------------------------ tests


@pytest.fixture(scope="module")
def result() -> dict:
    return run_imports()


def test_manifest_matches_files_per_file(result: dict) -> None:
    for name, f in M["files"].items():
        got = result["files"][name]
        assert got["rows"] == f["rows"], name
        assert got["invalid"] == f["invalid"], name
        assert got["created"] == f["created_donors"], name
        if "valid_gifts" in f:
            assert got["gifts"] == f["valid_gifts"], name
            assert got["cents"] == f["gross_cents"], name
            assert got["attr"] == f["by_attribution"], name
            assert sum(a["rows"] for a in got["attr"].values()) + len(got["invalid"]) == got["rows"]
            for component in ("donation_cents", "match_cents"):
                assert sum(a[component] for a in got["attr"].values()) == f[component], name
            assert f["gross_cents"] == f["donation_cents"] + f["match_cents"]


def test_manifest_totals_donors_and_review_items(result: dict) -> None:
    assert result["donors"] == M["donors_created_after_all_imports"]
    assert sum(f["gifts"] for f in result["files"].values()) == M["totals"]["valid_gifts"]
    assert sum(f["cents"] for f in result["files"].values()) == M["totals"]["gross_cents"]
    key = lambda x: (x["file"], x["row"])  # noqa: E731
    assert sorted(result["review"], key=key) == sorted(M["review_items"], key=key)


def test_benevity_row_and_gift_counts_and_revenue_are_independent() -> None:
    f = M["files"][BENEVITY]
    assert (f["rows"], f["valid_gifts"]) == (80, 91)
    assert f["donation_cents"] == 597500 and f["match_cents"] == 101250
    assert f["gross_cents"] == 698750
    assert f["by_attribution"]["anonymous"]["gifts"] == 13
    assert M["totals"]["valid_gifts"] == 531
    assert M["totals"]["gross_cents"] == 12943750
    assert M["donors_created_after_all_imports"] == 225
    assert len(M["review_items"]) == 19
    assert sum(len(f["invalid"]) for f in M["files"].values()) == 14


def test_retention_counts_only_employee_donations(result: dict) -> None:
    linked_revenue = sum(
        f["by_attribution"]["linked"]["cents"] for f in M["files"].values() if "by_attribution" in f
    )
    donor_giving = sum(cents for gifts in result["gifts"].values() for _, cents in gifts)
    linked_match = sum(
        f["by_attribution"]["linked"]["match_cents"]
        for f in M["files"].values()
        if "by_attribution" in f
    )
    assert linked_match == 92500
    assert donor_giving == linked_revenue - linked_match


def test_retention_classes_match_manifest(result: dict) -> None:
    as_of = date.fromisoformat(M["retention"]["as_of"])
    assert as_of == date.fromisoformat(M["demo_now"])
    assert retention(result["gifts"], as_of) == M["retention"]["classes"]


def test_row_counts_are_close_to_the_spec() -> None:
    f = M["files"]
    assert 120 <= f[SHEET]["rows"] <= 135  # ~120 donors and 6 funders
    assert 380 <= f[ZEFFY]["rows"] <= 450  # ~400 payments
    assert 70 <= f[BENEVITY]["rows"] <= 90  # ~80 rows
    assert 35 <= f[GENERIC]["rows"] <= 45  # ~40 rows


def test_fixtures_cover_the_designed_edge_cases(result: dict) -> None:
    codes = {i["code"] for f in M["files"].values() for i in f["invalid"]}
    assert codes == {"not_succeeded", "bad_date", "bad_amount", "non_positive_amount",
                     "non_usd", "refunded"}  # fmt: skip
    assert {r["reason"] for r in M["review_items"]} == {
        "household", "phone", "name_conflict", "name_employer"}  # fmt: skip
    assert M["files"][BENEVITY]["by_attribution"]["anonymous"]["gifts"] >= 10
    # two identical same-day gifts without a transaction id stay two gifts (row_key occurrence)
    twins = [(r["Date"], r["Amount"], r["Donor name"], r["Email"]) for r in read_rows(GENERIC)
             if not r["Transaction ID"]]  # fmt: skip
    assert len(twins) != len(set(twins))
    assert all(v["donors"] > 0 for v in M["retention"]["classes"].values())


def test_benevity_file_uses_the_documented_glossary_columns() -> None:
    """Column names from the Causes Portal Reporting glossary (docs/IMPORT_FORMATS.md)."""
    headers = set(read_rows(BENEVITY)[0])
    documented = {
        "Disbursement ID", "Disbursement Date", "Company Name", "Transaction ID",
        "Donation Date", "Donation Amount", "Match Amount", "Donation Currency",
        "Foreign Exchange Rate", "Cause Support Fee", "Merchant Fee", "Donation Frequency",
        "Donation Type", "Donor First Name", "Donor Last Name", "Donor Email",
        "Donor Zip / Postal Code",
    }  # fmt: skip
    assert documented <= headers
    rows = read_rows(BENEVITY)
    assert any(Decimal(r["Match Amount"]) > 0 for r in rows)  # employer matches exist
    assert any(re.fullmatch(r"[A-Z]\d{4}", r["Company Name"]) for r in rows)  # anonymous companies
    assert any(Decimal(r["Merchant Fee"]) > 0 for r in rows)  # fees exist
    assert all(r["Donor Zip / Postal Code"] for r in rows)  # zip defaults to visible


def test_synthetic_contact_data_only() -> None:
    """Privacy rule: only reserved or fictional domains and 555-01xx phone numbers."""
    domains, phones = set(), set()
    for name in M["import_order"]:
        for r in read_rows(name):
            for col, val in r.items():
                if "mail" in col.lower() and val and "@" in val:
                    domains.add(val.split("@")[1].lower())
                if col == "Phone" and val:
                    phones.add(norm_phone(val)[-7:])
    assert domains <= {"example.org", "example.com", "mail.test", "workmail.test", "corp.test"}
    assert all(p.startswith("55501") for p in phones), phones


def test_files_match_manifest_hashes() -> None:
    for name, f in M["files"].items():
        assert hashlib.sha256((FIX / name).read_bytes()).hexdigest() == f["sha256"], name


def _generator():
    spec = importlib.util.spec_from_file_location("cic_fixture_generator", FIX / "generate.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_generator_is_deterministic_and_committed_files_are_current(tmp_path: Path) -> None:
    gen = _generator()
    a, b = tmp_path / "a", tmp_path / "b"
    gen.generate(a)
    gen.generate(b)
    for name in [*M["import_order"], "manifest.json"]:
        assert (a / name).read_bytes() == (b / name).read_bytes(), f"{name} differs between runs"
        assert (a / name).read_bytes() == (FIX / name).read_bytes(), (
            f"{name} is stale: run `python fixtures/generate.py`"
        )
