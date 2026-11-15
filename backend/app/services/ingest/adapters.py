"""Assumed source layouts from IMPORT_FORMATS.md; one record per physical data row."""

import re
from datetime import date

from pydantic import BaseModel, Field

from app.errors import Invalid
from app.schemas.common import DonorKind, ImportSource
from app.services.ingest import normalizers as norm
from app.services.ingest.uploads import has_value, read_table


class IncomingDonor(BaseModel):
    display_name: str = ""
    first_name: str = ""
    last_name: str = ""
    kind: DonorKind = "person"
    organization: str = ""
    email: str = ""
    phone: str = ""
    zeffy_contact: str = ""
    notes: str = ""
    anonymous: bool = False


class IncomingGift(BaseModel):
    source_txn_id: str = ""
    source_platform: str = ""
    gift_date: date
    gross_cents: int
    fee_cents: int = 0
    net_cents: int
    campaign_name: str = ""
    is_matching_gift: bool = False
    payer_name: str = ""


class IncomingRow(BaseModel):
    row_number: int
    donor: IncomingDonor = Field(default_factory=IncomingDonor)
    gifts: list[IncomingGift] = Field(default_factory=list)
    reason: str | None = None
    disbursement_id: str = ""
    disbursement_date: str = ""


REQUIRED = {
    "spreadsheet": ["Name"],
    "zeffy": ["Payment ID", "Date", "Amount"],
    "benevity": ["Transaction ID", "Donation Date", "Donation Amount", "Donation Currency"],
    "generic": ["Date", "Amount", "Platform"],
}


def header(value: object) -> str:
    return re.sub(r"[\s_-]+", " ", str(value or "").strip().lower())


def _donor(source: ImportSource, row: dict[str, object]) -> IncomingDonor:
    def get(key: str) -> str:
        return str(row.get(header(key)) or "").strip()

    if source == "spreadsheet":
        full, first, last = get("Name"), get("First name"), get("Last name")
        kind: dict[str, DonorKind] = {
            "individual": "person",
            "organization": "organization",
            "funder": "funder",
        }
        donor_kind = kind.get(get("Type").lower() or "individual")
        if donor_kind is None:
            raise ValueError("bad_donor_type")
        donor = IncomingDonor(display_name=full, kind=donor_kind)
    elif source in ("zeffy", "benevity"):
        prefix = "Donor " if source == "benevity" else ""
        first, last = get(prefix + "First name"), get(prefix + "Last name")
        full = f"{first} {last}".strip()
        donor = IncomingDonor(display_name=full)
    else:
        full, first, last = get("Donor name"), "", ""
        donor = IncomingDonor(display_name=full)
    if not first and not last:
        parts = full.rsplit(maxsplit=1)
        first, last = (parts[0], parts[1]) if len(parts) == 2 else (full, "")
    donor.first_name, donor.last_name = first, last
    if donor.kind != "person":
        donor.first_name, donor.last_name = full, ""
    prefix = "Donor " if source == "benevity" else ""
    donor.email = norm.email(get(prefix + "Email"))
    donor.phone = norm.phone(get("Phone")) if source != "benevity" else ""
    donor.organization = get("Company Name" if source == "benevity" else "Organization")
    if source == "benevity" and re.fullmatch(r"[A-Z]\d{4}", donor.organization):
        donor.organization = ""
    donor.zeffy_contact = get("Contact ID") if source == "zeffy" else ""
    donor.notes = get("Notes") if source == "spreadsheet" else ""
    donor.anonymous = source != "spreadsheet" and not (full or donor.email)
    if source == "spreadsheet" and not full:
        raise ValueError("missing_name")
    return donor


def _record(source: ImportSource, n: int, row: dict[str, object]) -> IncomingRow:
    def get(key: str, default: object = "") -> object:
        value = row.get(header(key))
        return value if value is not None and value != "" else default

    result = IncomingRow(row_number=n)
    if source == "benevity":
        result.disbursement_id = str(get("Disbursement ID"))
        result.disbursement_date = str(get("Disbursement Date"))
    try:
        if source == "zeffy":
            if str(get("Payment status", "succeeded")).lower() != "succeeded":
                raise ValueError("not_succeeded")
            if str(get("Currency", "USD")).upper() != "USD":
                raise ValueError("non_usd")
            if norm.cents(get("Refunded amount", "0"), positive=False):
                raise ValueError("refunded")
        if source == "benevity" and str(get("Donation Currency")).upper() != "USD":
            raise ValueError("non_usd")
        if source == "spreadsheet":
            result.donor = _donor(source, row)
            return result
        benevity = source == "benevity"
        when = norm.gift_date(get("Donation Date" if benevity else "Date"))
        gross = norm.cents(get("Donation Amount" if benevity else "Amount"))
        fee = (
            (
                norm.cents(get("Cause Support Fee", "0"), positive=False)
                + norm.cents(get("Merchant Fee", "0"), positive=False)
            )
            if benevity
            else (norm.cents(get("Fee", "0"), positive=False) if source == "generic" else 0)
        )
        if fee > gross:
            raise ValueError("fees_exceed_amount")
        txn = str(get("Payment ID" if source == "zeffy" else "Transaction ID")).strip()
        if source in ("zeffy", "benevity") and not txn:
            raise ValueError("missing_transaction_id")
        platform = str(get("Platform")).strip().lower() if source == "generic" else ""
        if source == "generic" and platform not in {"azgives", "united_way", "other"}:
            raise ValueError("bad_platform")
        result.donor = _donor(source, row)
        gift = IncomingGift(
            source_txn_id=txn,
            source_platform=platform,
            gift_date=when,
            gross_cents=gross,
            fee_cents=fee,
            net_cents=gross - fee,
            campaign_name=str(get("Project Name" if benevity else "Campaign")).strip(),
            payer_name=str(get("Company Name")).strip() if benevity else "",
        )
        gifts = [gift]
        if benevity:
            match = norm.cents(get("Match Amount", "0"), positive=False)
            if match:
                gifts.append(
                    gift.model_copy(
                        update={
                            "source_txn_id": txn + ":match",
                            "gross_cents": match,
                            "fee_cents": 0,
                            "net_cents": match,
                            "is_matching_gift": True,
                        }
                    )
                )
        result.gifts = gifts
    except ValueError as exc:
        result.reason = str(exc)
    return result


def parse_upload(source: ImportSource, filename: str, data: bytes) -> list[IncomingRow]:
    table = read_table(filename, data)
    if not table:
        raise Invalid("File has no header row.")
    header_number, header_cells = table[0]
    headers = [header(h) for h in header_cells]
    named_headers = [h for h in headers if h]
    if len(named_headers) != len(set(named_headers)):
        raise Invalid("File has duplicate column names.")
    missing = [h for h in REQUIRED[source] if header(h) not in headers]
    if missing:
        raise Invalid("Missing required columns: " + ", ".join(missing))
    result = []
    for source_number, values in table[1:]:
        n = source_number - header_number
        extras = (
            value
            for index, value in enumerate(values)
            if index >= len(headers) or not headers[index]
        )
        if any(has_value(value) for value in extras):
            result.append(IncomingRow(row_number=n, reason="extra_cells"))
        else:
            row = {key: value for key, value in zip(headers, values, strict=False) if key}
            result.append(_record(source, n, row))
    return result
