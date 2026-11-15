#!/usr/bin/env python3
"""Deterministic synthetic fixtures for CIC Compass. Every person here is made up.

    python fixtures/generate.py            # (re)write the files next to this script
    python fixtures/generate.py --out DIR  # write somewhere else

Writes the donor spreadsheet, three gift files (Zeffy-like, Benevity-like, generic) and
manifest.json. Column layouts are the ASSUMED ones in docs/IMPORT_FORMATS.md; none of these
files is a real platform export. The same seed always produces byte-identical files.

Each row is generated together with its designed outcome (new donor, linked, needs review,
anonymous, invalid), and manifest.json is derived from those outcomes. tests/integration/
test_fixtures.py recomputes everything from the files alone with an independent resolver.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20261114
DEMO_NOW = date(2026, 11, 15)  # "today" for retention in the manifest and the demo
DATA_START = date(2024, 5, 1)
DATA_END = date(2026, 10, 31)

FIRST = ["Ada", "Amara", "Andre", "Beatriz", "Caleb", "Camila", "Dario", "Deja", "Elena", "Emeka",
         "Farah", "Gabriel", "Grace", "Hana", "Hector", "Imani", "Isaac", "Jamal", "Jasmine",
         "José", "Kai", "Katherine", "Keiko", "Lena", "Liam", "Lucia", "Malik", "Maya", "Mateo",
         "Nadia", "Noah", "Olivia", "Omar", "Priya", "Quinn", "Rafael", "Renata", "Samir",
         "Sofia", "Tariq", "Valeria", "Wei", "Xavier", "Yara", "Zoë"]  # fmt: skip
LAST = ["Alvarez", "Banerjee", "Brooks", "Castillo", "Chen", "Delgado", "Edwards", "Farouk",
        "Garcia", "Haddad", "Ibrahim", "Jackson", "Kim", "Lopez", "Mbeki", "Nakamura", "Okafor",
        "Patel", "Quintero", "Ramirez", "Singh", "Tanaka", "Underwood", "Vargas", "Washington",
        "Xu", "Yoder", "Zhang", "Whitfield", "Moreno", "Nguyen", "Oduya", "Peralta", "Rojas",
        "Sandoval", "Thompson", "Valdez", "Wallace", "Yamamoto", "Ziegler"]  # fmt: skip
EMPLOYERS = ["Sonoran Aerospace Inc", "Desert Ridge Health", "Cactus Software LLC",
             "Phoenix Water Works", "Saguaro Logistics", "Copper State Energy",
             "Mesa Medical Group", "Red Rock Analytics"]  # fmt: skip
ORGS = ["Saguaro Credit Union", "Palo Verde Dental", "Camelback Coffee Co", "Tempe Tutoring",
        "Ocotillo Design Studio", "Chandler Bike Shop", "Scottsdale Print House",
        "Gilbert Garden Supply", "Mesa Makers Guild", "Verde Valley Books", "Agave Catering",
        "Roosevelt Row Gallery", "Arcadia Pilates", "Encanto Bakery", "Sunnyslope Hardware",
        "Papago Pottery", "South Mountain Cycles", "Apache Trail Tours", "Ahwatukee Optical",
        "Cave Creek Candles"]  # fmt: skip
FUNDERS = [
    "Desert Sky Foundation",
    "Copper State Community Fund",
    "Sonoran Tech Giving Circle",
    "Valley Youth Futures Trust",
    "Saguaro Family Foundation",
    "Camelback Impact Fund",
]
CAMPAIGNS = [
    ("AI Academy Fall 2025", "AI Academy"), ("AI Academy Spring 2026", "AI Academy"),
    ("K12 Program Support", "K12 Program"), ("Summer Camp 2026", "Summer Camp"),
    ("Day of Compute 2025", "Day of Compute"), ("Year-End Appeal", None), ("Donate", None),
]  # fmt: skip
AMOUNTS = [2500, 5000, 7500, 10000, 15000, 25000, 50000, 100000]

# Stable codes for invalid rows; the adapters may word their messages differently.
BAD_DATE, BAD_AMOUNT, NON_POSITIVE = "bad_date", "bad_amount", "non_positive_amount"
NON_USD, NOT_SUCCEEDED, REFUNDED = "non_usd", "not_succeeded", "refunded"

FILES = ["synthetic_cic_spreadsheet.xlsx", "synthetic_zeffy_like.csv",
         "synthetic_benevity_like.csv", "synthetic_generic_azgives_like.csv"]  # fmt: skip
HEADERS = {
    "sheet": ["Name", "Type", "First name", "Last name", "Organization", "Email", "Phone",
              "Notes"],
    "zeffy": ["Payment ID", "Date", "Amount", "Currency", "Payment status", "Refunded amount",
              "Campaign", "Contact ID", "First name", "Last name", "Email", "Phone"],
    "benevity": ["Disbursement ID", "Transaction ID", "Donation Date", "Donation Type",
                 "Company", "Donor First Name", "Donor Last Name", "Email", "Benevity Donor ID",
                 "Cause", "Currency", "Amount", "Fee"],
    "generic": ["Date", "Amount", "Platform", "Donor name", "Email", "Phone", "Organization",
                "Campaign", "Transaction ID", "Fee", "Notes"],
}  # fmt: skip


@dataclass
class P:
    pid: int
    kind: str  # person | organization | funder
    first: str | None
    last: str | None
    name: str
    employer: str | None = None
    email: str | None = None
    phone: str | None = None
    zeffy_id: str | None = None
    benevity_id: str | None = None


@dataclass
class Row:
    """A file row plus its designed outcome."""

    cells: dict[str, str]
    when: date | None
    cents: int = 0
    pid: int | None = None
    # linked | pending_review | anonymous | invalid | donor (spreadsheet row)
    attr: str = "linked"
    why: str | None = None  # review reason or invalid code


# ---------------------------------------------------------------- people


class World:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.people: list[P] = []
        pairs = sorted((f, last) for f in FIRST for last in LAST)
        rng.shuffle(pairs)
        self._pairs = iter(pairs)
        self._orgs, self._funders = list(ORGS), list(FUNDERS)
        self._emails: set[str] = set()
        self._phones: set[str] = set()

    def phone(self) -> str:
        while True:
            p = f"{self.rng.choice(['480', '602', '520', '928'])}555{self.rng.randrange(100):04d}"
            p = p[:6] + "01" + p[8:]  # 555-01xx is reserved for fiction
            if p not in self._phones:
                self._phones.add(p)
                return p

    def email(self, stem: str, domain: str = "example.org") -> str:
        base, n = stem.lower().replace(" ", "."), 0
        while True:
            addr = f"{base}{n or ''}@{domain}"
            if addr not in self._emails:
                self._emails.add(addr)
                return addr
            n += 1

    def add(self, kind: str = "person", employer: bool = False) -> P:
        pid = len(self.people) + 1
        if kind == "person":
            first, last = next(self._pairs)
            p = P(pid, kind, first, last, f"{first} {last}")
            p.email = self.email(
                f"{first}.{last}".replace("é", "e").replace("ë", "e"),
                self.rng.choice(["example.org", "example.com", "mail.test"]),
            )
            p.phone = self.phone()
            if employer:
                p.employer = self.rng.choice(EMPLOYERS)
        else:
            name = (self._orgs if kind == "organization" else self._funders).pop(0)
            p = P(pid, kind, None, None, name)
            p.email = self.email(
                ("hello." if kind == "organization" else "grants.") + name.split()[0]
            )
            p.phone = self.phone()
        p.zeffy_id = f"zc_{pid:05d}"
        self.people.append(p)
        return p


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def fmt_phone(p: str, style: int) -> str:
    d = p[-10:]
    return [f"({d[:3]}) {d[3:6]}-{d[6:]}", f"{d[:3]}-{d[3:6]}-{d[6:]}", f"+1{d}"][style % 3]


def typo(name: str) -> str:
    """A small slip that keeps the first initial and the last name, so matching still works."""
    first, _, last = name.partition(" ")
    if len(first) < 4:
        return name
    i = len(first) // 2
    return f"{first[:i]}{first[i]}{first[i:]} {last}"  # doubled letter: "Camila" -> "Camiila"


def rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randrange((end - start).days + 1))


def gifts_for(rng: random.Random, pattern: str) -> list[tuple[date, int]]:
    """Gift history shaped to land in a retention class as of DEMO_NOW (DATA_MODEL 3.5)."""
    t = DEMO_NOW
    cur = (t - timedelta(days=364), DATA_END)
    prev = (t - timedelta(days=729), t - timedelta(days=366))
    old = (DATA_START, t - timedelta(days=731))
    a = rng.choice(AMOUNTS[:6])
    d = lambda w: rand_date(rng, *w)  # noqa: E731
    return {
        "new": [(d(cur), a)] + ([(d(cur), a)] if rng.random() < 0.4 else []),
        "lapsed": [(d(prev), a)],
        "same": [(d(prev), a), (d(cur), a)],
        "increased": [(d(prev), a), (d(cur), 2 * a)],
        "decreased": [(d(prev), 2 * a), (d(cur), a)],
        "reactivated": [(d(old), a), (d(cur), a)],
        "old_only": [(d(old), a)],
    }[pattern]


def monthly(rng: random.Random) -> list[tuple[date, int]]:
    start = rand_date(rng, date(2024, 6, 1), date(2026, 3, 1))
    day, amount, out = rng.randrange(1, 29), rng.choice(AMOUNTS[:4]), []
    y, m = start.year, start.month
    for _ in range(rng.randrange(6, 15)):
        g = date(y, m, day)
        if g > DATA_END:
            break
        out.append((g, amount))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


PATTERNS = ["new", "lapsed", "same", "increased", "decreased", "reactivated", "old_only"]


# ---------------------------------------------------------------- the four files


def build(seed: int = SEED) -> tuple[dict[str, list[Row]], World]:
    rng = random.Random(seed)
    w = World(rng)

    # Spreadsheet donors: 100 people (35 with an employer), 20 organizations, 6 funders.
    persons = [w.add(employer=i < 35) for i in range(100)]
    orgs = [w.add("organization") for _ in range(20)]
    funders = [w.add("funder") for _ in range(6)]
    rng.shuffle(persons)
    employed = [p for p in persons if p.employer]
    others = [p for p in persons if not p.employer]
    # Roles. Employed people first so eight of them can appear in Zeffy and Benevity.
    zeffy_link = employed[:8] + others[:36] + employed[8:24]  # 60 people matched by email
    no_email = [p for p in others[36:44]]  # 8 people with no email in the spreadsheet
    conflict = others[44:46]  # same email as the sheet, different last name in Zeffy
    generic_link = others[46:54]
    for p in no_email:
        p.email = None

    # Households: the second member shares an email with a person who never gives.
    households = []
    for p in others[54:57]:
        second = w.add(employer=False)
        while second.first[0] == p.first[0]:  # a different first initial, so it is a real conflict
            w.people.pop()
            second = w.add(employer=False)
        second.last, second.name = p.last, f"{second.first} {p.last}"
        second.email = p.email
        households.append(second)

    rows: dict[str, list[Row]] = {"sheet": [], "zeffy": [], "benevity": [], "generic": []}

    # --- spreadsheet
    sheet_people = persons + orgs + funders
    rng.shuffle(sheet_people)
    for h in households:  # the second member always comes after the original row
        original = next(p for p in sheet_people if p.email == h.email)
        sheet_people.insert(
            rng.randrange(sheet_people.index(original) + 1, len(sheet_people) + 1), h
        )
    typo_for = {p.pid for p in rng.sample([x for x in persons if x not in employed[:8]], 10)}
    for i, p in enumerate(sheet_people):
        name = (
            typo(p.name)
            if p.pid in typo_for and p.pid not in {h.pid for h in households}
            else p.name
        )
        kind = {"person": "Individual", "organization": "Organization", "funder": "Funder"}[p.kind]
        pending = p in households
        rows["sheet"].append(Row(
            {"Name": name, "Type": kind, "First name": p.first or "", "Last name": p.last or "",
             "Organization": p.employer or "", "Email": (p.email or "").upper() if i % 9 == 0 else (p.email or ""),
             "Phone": fmt_phone(p.phone, i) if p.phone and (i % 7 or p in no_email[:6]) else "",
             "Notes": "shared household email" if pending else ("" if i % 5 else "met at Day of Compute")},
            None, 0, p.pid, "pending_review" if pending else "donor", "household" if pending else None,
        ))  # fmt: skip

    # --- Zeffy-like
    zeffy_only = [w.add() for _ in range(60)]
    for p in zeffy_only:
        p.phone = w.phone()
    given: dict[int, list[tuple[date, int]]] = {}
    recurring = {p.pid for p in zeffy_link[:22]}
    for p in zeffy_link + zeffy_only:
        pat = rng.choice(PATTERNS)
        given[p.pid] = monthly(rng) if p.pid in recurring else gifts_for(rng, pat)
    by_pid = {p.pid: p for p in w.people}

    def zrow(p: P, when: date, cents: int, **over: str) -> Row:
        camp, _ = rng.choice(CAMPAIGNS)
        cells = {"Payment ID": f"pay_{rng.getrandbits(40):010x}", "Date": when.isoformat(),
                 "Amount": money(cents), "Currency": "USD", "Payment status": "succeeded",
                 "Refunded amount": "0.00", "Campaign": camp, "Contact ID": p.zeffy_id or "",
                 "First name": p.first or "", "Last name": p.last or "", "Email": p.email or "",
                 "Phone": fmt_phone(p.phone, 1) if p.phone else ""} | over  # fmt: skip
        return Row(cells, when, cents, p.pid)

    zr = rows["zeffy"]
    for pid, items in given.items():
        for when, cents in items:
            zr.append(zrow(by_pid[pid], when, cents))
    # Phone-only matches: same phone as a sheet donor, a new email, one payment each -> review.
    for p in no_email[:6]:
        alt = P(
            p.pid,
            p.kind,
            p.first,
            p.last,
            p.name,
            email=w.email(f"{p.first}.{p.last}.home".replace("é", "e").replace("ë", "e")),
            phone=p.phone,
            zeffy_id=f"zc_alt_{p.pid:05d}",
        )
        row = zrow(alt, rand_date(rng, date(2025, 12, 1), DATA_END), rng.choice(AMOUNTS[:4]))
        row.attr, row.why = "pending_review", "phone"
        zr.append(row)
    # Same email, different surname (name conflict) -> review.
    for p in conflict:
        alt = P(
            p.pid,
            p.kind,
            p.first,
            "Whitaker-Reyes",
            p.name,
            email=p.email,
            phone=None,
            zeffy_id=f"zc_alt_{p.pid:05d}",
        )
        row = zrow(alt, rand_date(rng, date(2026, 1, 1), DATA_END), 5000)
        row.attr, row.why = "pending_review", "name_conflict"
        zr.append(row)
    # Invalid rows: each says why. Contact details belong to people who also have valid rows.
    donors_z = zeffy_link[8:15]
    bad = [
        ({"Payment status": "failed"}, NOT_SUCCEEDED), ({"Payment status": "failed"}, NOT_SUCCEEDED),
        ({"Payment status": "pending"}, NOT_SUCCEEDED), ({"Date": "31/31/2025"}, BAD_DATE),
        ({"Amount": "twelve"}, BAD_AMOUNT), ({"Currency": "CAD"}, NON_USD),
        ({"Refunded amount": "25.00"}, REFUNDED),
    ]  # fmt: skip
    for (over, code), p in zip(bad, donors_z, strict=True):
        row = zrow(p, rand_date(rng, date(2025, 6, 1), DATA_END), 5000, **over)
        row.attr, row.why = "invalid", code
        if code in (BAD_DATE, BAD_AMOUNT):
            row.when, row.cents = None, 0
        zr.append(row)
    # Real exports are chronological; the bad-date row sorts last.
    zr.sort(
        key=lambda r: (
            r.cells["Date"] if r.cells["Date"][:2] == "20" else "9999",
            r.cells["Payment ID"],
        )
    )

    # --- Benevity-like
    bv = rows["benevity"]
    disb = [f"DISB-{n}" for n in ("2025-03", "2025-06", "2025-09", "2025-12", "2026-03", "2026-06")]
    disb_date = [date(2025, 3, 15), date(2025, 6, 15), date(2025, 9, 15), date(2025, 12, 15),
                 date(2026, 3, 15), date(2026, 6, 15)]  # fmt: skip
    txn = iter(range(700000, 800000))

    def brow(
        p: P | None,
        i: int,
        cents: int,
        *,
        kind: str = "User Portfolio Donation",
        company: str | None = None,
        email: str | None = "",
        bid: str = "",
        **over: str,
    ) -> Row:
        company = (
            company
            if company is not None
            else (p.employer if p and p.employer else "Sonoran Aerospace Inc")
        )
        when = disb_date[i] - timedelta(days=rng.randrange(1, 28))
        cells = {"Disbursement ID": disb[i], "Transaction ID": f"BV-{next(txn)}", "Donation Date": when.isoformat(),
                 "Donation Type": kind, "Company": company,
                 "Donor First Name": (p.first or p.name) if p else "", "Donor Last Name": (p.last or "") if p else "",
                 "Email": (p.email if email == "" else email) if p else "", "Benevity Donor ID": bid,
                 "Cause": rng.choice(["AI Academy", "K12 Program", "Summer Camp", "Coding in Color"]),
                 "Currency": "USD", "Amount": money(cents), "Fee": "0.00"} | over  # fmt: skip
        return Row(cells, when, cents, p.pid if p else None, "linked" if p else "anonymous")

    # Eight sheet donors with an employer: same name and employer, a work email -> review.
    for p in employed[:8]:
        work = w.email(f"{p.first}.{p.last}".replace("é", "e").replace("ë", "e"), "workmail.test")
        row = brow(p, rng.randrange(6), rng.choice(AMOUNTS[:5]), email=work, company=p.employer)
        row.attr, row.why = "pending_review", "name_employer"
        bv.append(row)
    # Six donors seen in Zeffy under the same email: auto-link.
    for p in zeffy_link[14:20]:
        bv.append(brow(p, rng.randrange(6), rng.choice(AMOUNTS[:5])))
    # Six repeat donors with a Benevity id: the first row creates, later rows link by id.
    repeaters = [w.add(employer=True) for _ in range(6)]
    for p in repeaters:
        p.benevity_id = f"bd_{p.pid:05d}"
        for i in sorted(rng.sample(range(6), 3)):
            bv.append(brow(p, i, rng.choice(AMOUNTS[:5]), bid=p.benevity_id,
                           email=w.email(f"{p.first}.{p.last}".replace("é", "e").replace("ë", "e"), "corp.test") if i % 2 else p.email))  # fmt: skip
    # Twenty new donors, two gifts each for the first fourteen; four employer matches among them.
    fresh = [w.add(employer=True) for _ in range(20)]
    for n, p in enumerate(fresh):
        for _ in range(2 if n < 14 else 1):
            kind = "Match" if n < 4 else "User Portfolio Donation"
            bv.append(
                brow(p, rng.randrange(6), rng.choice(AMOUNTS[:5]), kind=kind, company=p.employer)
            )
    # Ten anonymous gifts (donor details hidden) and two match rows with no donor.
    for n in range(10):
        bv.append(brow(None, rng.randrange(6), rng.choice(AMOUNTS[:4]), kind="Anonymous Donation"))
    for n in range(2):
        bv.append(
            brow(
                None, rng.randrange(6), rng.choice(AMOUNTS[1:5]), kind="Match", company=EMPLOYERS[n]
            )
        )
    # Two invalid rows.
    for over, code in [
        ({"Donation Date": "2025-13-45"}, BAD_DATE),
        ({"Amount": "0.00"}, NON_POSITIVE),
    ]:
        row = brow(
            repeaters[0],
            rng.randrange(6),
            0 if code == NON_POSITIVE else 5000,
            bid=repeaters[0].benevity_id,
            **over,
        )
        row.attr, row.why = "invalid", code
        if code == BAD_DATE:
            row.when, row.cents = None, 0
        bv.append(row)
    bv.sort(key=lambda r: (r.cells["Disbursement ID"], r.cells["Transaction ID"]))

    # --- generic (AZ Gives and United Way style)
    gr = rows["generic"]

    def grow(
        p: P | None,
        when: date,
        cents: int,
        platform: str = "azgives",
        *,
        txn_id: bool = True,
        name: str | None = None,
        **over: str,
    ) -> Row:
        cells = {"Date": when.isoformat(), "Amount": money(cents), "Platform": platform,
                 "Donor name": (name if name is not None else p.name) if p else "",
                 "Email": (p.email or "") if p else "", "Phone": "", "Organization": (p.employer or "") if p else "",
                 "Campaign": rng.choice(["AZ Gives Day 2025", "AZ Gives Day 2026", "Workplace giving", ""]),
                 "Transaction ID": f"{platform[:2].upper()}-{rng.getrandbits(32):08x}" if txn_id else "",
                 "Fee": "0.00", "Notes": ""} | over  # fmt: skip
        return Row(cells, when, cents, p.pid if p else None, "linked" if p else "anonymous")

    for p in funders:
        for _ in range(2 + (p.pid % 2)):
            gr.append(
                grow(
                    p,
                    rand_date(rng, date(2025, 1, 1), DATA_END),
                    rng.choice([250000, 500000, 1000000]),
                    "other",
                )
            )
    for p in generic_link:
        gr.append(
            grow(
                p, rand_date(rng, date(2025, 3, 1), DATA_END), rng.choice(AMOUNTS[:5]), name=p.name
            )
        )
    gen_new = [w.add() for _ in range(12)]
    for n, p in enumerate(gen_new):
        if n >= 9:
            p.email = None  # name-only donors: always a new donor, never matched by name
        gr.append(grow(p, rand_date(rng, date(2025, 3, 1), DATA_END), rng.choice(AMOUNTS[:5]),
                       "united_way" if n % 3 == 0 else "azgives", txn_id=n % 2 == 0))  # fmt: skip
    # Two genuinely identical gifts on the same day, no transaction id: both stay (DATA_MODEL 3.1).
    twin = w.add()
    when = date(2026, 4, 7)
    for _ in range(2):
        gr.append(grow(twin, when, 5000, txn_id=False))
    for over, code in [
        ({"Date": "April 7th"}, BAD_DATE),
        ({"Amount": "(12.00)"}, NON_POSITIVE),
        ({"Amount": ""}, BAD_AMOUNT),
    ]:
        row = grow(gen_new[0], date(2026, 2, 2), 1200, **over)
        row.attr, row.why = "invalid", code
        row.when, row.cents = None, 0
        gr.append(row)
    gr.sort(
        key=lambda r: (
            r.cells["Date"] if r.cells["Date"][:2] == "20" else "9999",
            r.cells["Transaction ID"],
            r.cells["Amount"],
        )
    )
    return rows, w


# ---------------------------------------------------------------- writing


def write_csv(path: Path, headers: list[str], rows: list[Row]) -> None:
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=headers, lineterminator="\n")
    wr.writeheader()
    wr.writerows(r.cells for r in rows)
    path.write_bytes(buf.getvalue().encode("utf-8"))


def write_xlsx(path: Path, headers: list[str], rows: list[Row]) -> None:
    """Byte-stable XLSX: fixed document properties and fixed zip timestamps."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Donors"
    ws.append(headers)
    for r in rows:
        ws.append([r.cells[h] for h in headers])
    wb.properties.creator = "CIC Compass synthetic fixtures"
    wb.properties.created = wb.properties.modified = datetime(2026, 11, 14, 12, 0, 0)
    raw = io.BytesIO()
    wb.save(raw)
    out = io.BytesIO()
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(src.namelist()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 14, 12, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o600 << 16
            info.create_system = 3  # "Unix" everywhere; Windows would record 0 and change the bytes
            data = src.read(name)
            if name == "docProps/core.xml":  # openpyxl stamps "modified" with the current time
                data = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2026-11-14T12:00:00Z", data
                )
            dst.writestr(info, data)
    path.write_bytes(out.getvalue())


# ---------------------------------------------------------------- manifest


def retention(gifts: dict[int, list[tuple[date, int]]], as_of: date) -> dict[str, dict[str, int]]:
    """DATA_MODEL 3.5, rolling basis, linked gifts only."""
    cur0, prev0, ever = (
        as_of - timedelta(days=365),
        as_of - timedelta(days=730),
        as_of - timedelta(days=730),
    )
    out = {k: {"donors": 0, "cents_cur": 0, "cents_prev": 0}
           for k in ("new", "reactivated", "increased", "same", "decreased", "lapsed")}  # fmt: skip
    for items in gifts.values():
        cur = sum(c for d, c in items if cur0 < d <= as_of)
        prev = sum(c for d, c in items if prev0 < d <= cur0)
        before = any(d <= ever for d, _ in items)
        if cur > 0 and prev == 0:
            cls = "reactivated" if before else "new"
        elif cur > 0 and prev > 0:
            cls = "increased" if cur > prev else "decreased" if cur < prev else "same"
        elif prev > 0:
            cls = "lapsed"
        else:
            continue
        out[cls]["donors"] += 1
        out[cls]["cents_cur"] += cur
        out[cls]["cents_prev"] += prev
    return out


def manifest(rows: dict[str, list[Row]], hashes: dict[str, str]) -> dict:
    files, created, gifts, review = {}, {}, {}, []
    for key, name in zip(["sheet", "zeffy", "benevity", "generic"], FILES, strict=True):
        f = {"sha256": hashes[name], "rows": len(rows[key]), "invalid": [], "created_donors": 0}
        attr = {k: {"gifts": 0, "cents": 0} for k in ("linked", "pending_review", "anonymous")}
        for n, r in enumerate(rows[key], start=1):
            if r.attr == "invalid":
                f["invalid"].append({"row": n, "code": r.why})
            elif r.attr == "pending_review":
                review.append({"file": name, "row": n, "reason": r.why})
                if key != "sheet":
                    attr["pending_review"]["gifts"] += 1
                    attr["pending_review"]["cents"] += r.cents
            elif r.attr == "donor":
                created.setdefault(r.pid, name)
                f["created_donors"] += 1
            else:
                if r.attr == "linked":
                    if r.pid not in created:
                        created[r.pid] = name
                        f["created_donors"] += 1
                    gifts.setdefault(r.pid, []).append((r.when, r.cents))
                attr[r.attr]["gifts"] += 1
                attr[r.attr]["cents"] += r.cents
        if key != "sheet":
            f["valid_gifts"] = sum(v["gifts"] for v in attr.values())
            f["gross_cents"] = sum(v["cents"] for v in attr.values())
            f["by_attribution"] = attr
        files[name] = f
    total = {k: sum(f.get(k, 0) for f in files.values()) for k in ("valid_gifts", "gross_cents")}
    return {
        "note": "Synthetic data. Derived from designed row outcomes; see tests/integration/test_fixtures.py.",
        "seed": SEED,
        "demo_now": DEMO_NOW.isoformat(),
        "import_order": FILES,
        "files": files,
        "totals": total,
        "donors_created_after_all_imports": len(created),
        "review_items": review,
        "retention": {
            "as_of": DEMO_NOW.isoformat(),
            "basis": "rolling",
            "classes": retention(gifts, DEMO_NOW),
        },  # fmt: skip
    }


def generate(out: Path, seed: int = SEED) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows, _ = build(seed)
    write_xlsx(out / FILES[0], HEADERS["sheet"], rows["sheet"])
    for key, name in zip(["zeffy", "benevity", "generic"], FILES[1:], strict=True):
        write_csv(out / name, HEADERS[key], rows[key])
    hashes = {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in FILES}
    data = manifest(rows, hashes)
    # Bytes, not write_text: Windows would otherwise turn "\n" into "\r\n".
    (out / "manifest.json").write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
    return data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = ap.parse_args()
    m = generate(args.out)
    for name, f in m["files"].items():
        print(f"{name}: {f['rows']} rows, sha256 {f['sha256'][:12]}")
    print(
        f"donors created: {m['donors_created_after_all_imports']}, review items: {len(m['review_items'])}"
    )
