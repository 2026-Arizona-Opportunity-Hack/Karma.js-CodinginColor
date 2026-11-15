"""Bounded CSV/XLSX decoding. Reject binary disguises and expanded ZIP bombs."""

import csv
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook  # type: ignore[import-untyped]

from app.errors import AppError, Invalid

MAX_BYTES = 5 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_ROWS = 20_000


class UploadTooLarge(AppError):
    status, code = 413, "upload_too_large"


class UnsupportedUpload(AppError):
    status, code = 415, "unsupported_upload"


def read_table(filename: str, data: bytes) -> list[list[object]]:
    if len(data) > MAX_BYTES:
        raise UploadTooLarge("File must be at most 5 MB.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            text = data.decode("utf-8-sig")
            if any(ord(c) < 32 and c not in "\r\n\t" for c in text):
                raise ValueError("binary content")
            if text.lstrip().startswith(("%PDF", "PK", "<", "{")):
                raise ValueError("not CSV")
            table: list[list[object]] = []
            for row in csv.reader(StringIO(text, newline=""), strict=True):
                table.append(list(row))
                if len(table) > MAX_ROWS + 1:
                    raise Invalid("File exceeds 20,000 rows.")
            if not table:
                raise ValueError("empty file")
            return table
        except (UnicodeError, ValueError, csv.Error) as exc:
            raise UnsupportedUpload("Upload a UTF-8 comma-delimited CSV file.") from exc
    if suffix != ".xlsx":
        raise UnsupportedUpload("Upload a CSV or XLSX file.")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise UploadTooLarge("Expanded XLSX exceeds 50 MB.")
            if not {"[Content_Types].xml", "xl/workbook.xml"} <= set(archive.namelist()):
                raise ValueError("not an XLSX workbook")
        book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            table = []
            sheet = book.worksheets[0]
            # Do not trust declared dimensions in files produced by other exporters.
            sheet.reset_dimensions()
            for row in sheet.iter_rows(values_only=True):
                table.append(list(row))
                if len(table) > MAX_ROWS + 1:
                    raise Invalid("File exceeds 20,000 rows.")
            return table
        finally:
            book.close()
    except AppError:
        raise
    except (BadZipFile, ValueError, KeyError, OSError, IndexError, ParseError) as exc:
        raise UnsupportedUpload("Upload a valid XLSX workbook.") from exc
