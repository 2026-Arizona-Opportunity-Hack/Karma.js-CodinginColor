"""Source contracts, including malformed uploads and Benevity's two-gift rows."""

import csv
from datetime import UTC, date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook

from app.errors import Invalid
from app.services.ingest.adapters import parse_upload
from app.services.ingest.normalizers import cents, email, gift_date, name, phone
from app.services.ingest.uploads import MAX_BYTES, UnsupportedUpload, UploadTooLarge

FIX = Path(__file__).resolve().parents[3] / "fixtures"


def csv_bytes(headers, rows):
    out = StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def test_normalizers_preserve_identity_and_round_half_up():
    assert cents("$1,234.505") == 123451
    assert cents("0", positive=False) == 0
    for value in ("NaN", "Infinity", "(12.00)", "-1", "", "0", "oops"):
        with pytest.raises(ValueError):
            cents(value)
    assert email(" A.B+tag@EXAMPLE.ORG ") == "a.b+tag@example.org"
    assert phone("(602) 555-0100") == "+16025550100"
    assert phone("1-602-555-0100") == "+16025550100"
    assert phone("44 20 1234 5678") == "442012345678"
    assert name(" Dr. \uff21da  Jones! ") == "ada jones"


@pytest.mark.parametrize(
    "value", ["2026-11-14", "11/14/2026", "11/14/26", 46340, date(2026, 11, 14)]
)
def test_dates(value):
    assert gift_date(value) == date(2026, 11, 14)


def test_aware_dates_use_phoenix():
    assert gift_date(datetime(2026, 11, 15, 2, tzinfo=UTC)) == date(2026, 11, 14)
    with pytest.raises(ValueError):
        gift_date("31/31/2025")


@pytest.mark.parametrize(
    "filename,data,exc",
    [
        ("gifts.pdf", b"Date,Amount,Platform\n", UnsupportedUpload),
        ("gifts.csv", b"%PDF-1.7", UnsupportedUpload),
        ("gifts.csv", b"PK\x03\x04binary", UnsupportedUpload),
        ("gifts.csv", b"a\x00,b", UnsupportedUpload),
        ("gifts.xlsx", b"Date,Amount\n", UnsupportedUpload),
        ("gifts.csv", b"x" * (MAX_BYTES + 1), UploadTooLarge),
    ],
)
def test_reject_uploads(filename, data, exc):
    with pytest.raises(exc):
        parse_upload("generic", filename, data)


def test_random_zip_is_not_xlsx():
    out = BytesIO()
    with ZipFile(out, "w") as archive:
        archive.writestr("hello.txt", "hello")
    with pytest.raises(UnsupportedUpload):
        parse_upload("generic", "gifts.xlsx", out.getvalue())


def test_single_column_spreadsheet_is_valid_and_invalid_rows_are_retained():
    rows = parse_upload("spreadsheet", "donors.csv", b"Name\nAda Jones\n\n")
    assert len(rows) == 2
    assert rows[0].donor.display_name == "Ada Jones"
    assert rows[1].reason == "missing_name"


def test_duplicate_headers_and_extra_cells():
    with pytest.raises(Invalid, match="duplicate"):
        parse_upload("spreadsheet", "donors.csv", b"Name,NAME\nA,B\n")
    row = parse_upload("generic", "gifts.csv", b"Date,Amount,Platform\n2026-11-14,5,other,extra\n")[
        0
    ]
    assert row.reason == "extra_cells"


@pytest.mark.parametrize(
    "value,reason", [("-1", "non_positive_amount"), ("oops", "bad_amount"), ("NaN", "bad_amount")]
)
def test_invalid_benevity_match_rejects_entire_row(value, reason):
    data = csv_bytes(
        ["Transaction ID", "Donation Date", "Donation Amount", "Match Amount", "Donation Currency"],
        [["T1", "2026-11-14", "10", value, "USD"]],
    )
    row = parse_upload("benevity", "gifts.csv", data)[0]
    assert row.reason == reason
    assert not row.gifts


def test_headers_and_spreadsheet_never_create_gifts():
    data = csv_bytes(
        [" NAME ", "FIRST_name", "last-name", "EMAIL", "Ignored"],
        [["Ada Jones", "Ada", "Jones", " ADA@example.org ", "unused"]],
    )
    row = parse_upload("spreadsheet", "donors.CSV", data)[0]
    assert row.donor.email == "ada@example.org"
    assert row.donor.kind == "person"
    assert not row.gifts
    assert row.reason is None
    with pytest.raises(Invalid, match="Name"):
        parse_upload("spreadsheet", "donors.csv", b"Email\na@example.org\n")


def test_first_xlsx_sheet_and_excel_date():
    book = Workbook()
    sheet = book.active
    sheet.append(["Date", "Amount", "Platform"])
    sheet.append([datetime(2026, 11, 14), 12.345, "azgives"])
    book.create_sheet("ignored").append(["not", "data"])
    out = BytesIO()
    book.save(out)
    row = parse_upload("generic", "gifts.xlsx", out.getvalue())[0]
    assert row.gifts[0].gross_cents == 1235
    assert row.gifts[0].gift_date == date(2026, 11, 14)
    assert row.donor.anonymous


def test_benevity_match_and_fees_and_no_address_storage():
    data = csv_bytes(
        [
            "Transaction ID",
            "Donation Date",
            "Donation Amount",
            "Match Amount",
            "Donation Currency",
            "Cause Support Fee",
            "Merchant Fee",
            "Company Name",
            "Donor Zip / Postal Code",
            "Disbursement ID",
            "Disbursement Date",
        ],
        [["T1", "11/14/26", "100", "50", "USD", "2", "1.25", "A1234", "85001", "D1", "11/15/26"]],
    )
    row = parse_upload("benevity", "gifts.csv", data)[0]
    donation, match = row.gifts
    assert (donation.source_txn_id, donation.net_cents) == ("T1", 9675)
    assert (match.source_txn_id, match.gross_cents, match.fee_cents) == ("T1:match", 5000, 0)
    assert match.is_matching_gift and match.payer_name == "A1234"
    assert row.donor.anonymous and not row.donor.organization
    assert row.disbursement_id == "D1"
    assert "85001" not in row.model_dump_json()


def test_fixture_adapters_preserve_rows_reasons_and_match_gifts():
    import json

    manifest = json.loads((FIX / "manifest.json").read_text())
    gifts = invalid = anonymous = 0
    for source, filename in zip(
        ["spreadsheet", "zeffy", "benevity", "generic"], manifest["import_order"], strict=True
    ):
        rows = parse_upload(source, filename, (FIX / filename).read_bytes())
        expected = manifest["files"][filename]
        assert len(rows) == expected["rows"]
        assert [{"row": r.row_number, "code": r.reason} for r in rows if r.reason] == (
            expected["invalid"]
        )
        gifts += sum(len(r.gifts) for r in rows)
        invalid += sum(r.reason is not None for r in rows)
        if source == "benevity":
            anonymous = sum(len(r.gifts) for r in rows if r.donor.anonymous)
    assert (gifts, invalid, anonymous) == (531, 14, 13)
