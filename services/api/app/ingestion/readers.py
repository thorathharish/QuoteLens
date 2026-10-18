"""Read uploaded BOM files into plain string grids.

Only .xlsx, .csv and .tsv are accepted. XLSX is opened read-only with cached values
(formulas are never evaluated) and parsed with defusedxml installed, which openpyxl uses
automatically to block XML entity attacks.
"""

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import PurePath

from openpyxl import load_workbook

from app.domain.errors import FileTooLargeError, UnsupportedFileError, ValidationFailedError

MAX_ROWS = 5_000
MAX_COLUMNS = 60
_XLSX_MAGIC = b"PK\x03\x04"

Cell = str | None
Grid = list[list[Cell]]


@dataclass(frozen=True, slots=True)
class Workbook:
    """Sheet name → rows of cells, trailing empty rows and columns trimmed."""

    sheets: dict[str, Grid]


def read_bom_file(filename: str, data: bytes, max_bytes: int) -> Workbook:
    if len(data) > max_bytes:
        raise FileTooLargeError(
            f"File is {len(data) / 1_048_576:.1f} MB; the limit is {max_bytes / 1_048_576:.0f} MB"
        )
    if not data:
        raise ValidationFailedError("The uploaded file is empty")

    suffix = PurePath(filename).suffix.lower()
    if suffix == ".xlsx":
        return _read_xlsx(data)
    if suffix in {".csv", ".tsv", ".txt"}:
        return Workbook(sheets={"CSV": _read_delimited(data, tab=suffix == ".tsv")})
    if suffix == ".xls":
        raise UnsupportedFileError("Legacy .xls is not supported; save the file as .xlsx")
    raise UnsupportedFileError(
        f"Unsupported file type '{suffix or filename}'; use .xlsx, .csv or .tsv"
    )


_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


def _read_xlsx(data: bytes) -> Workbook:
    if data.startswith(_OLE_MAGIC):
        raise UnsupportedFileError(
            "This workbook is password-protected (or saved in the old Excel format). Open it in "
            "Excel, remove the password under File > Info > Protect Workbook, save as .xlsx and "
            "upload it again."
        )
    if not data.startswith(_XLSX_MAGIC):
        raise UnsupportedFileError("File has an .xlsx extension but is not an Excel workbook")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise UnsupportedFileError("The Excel workbook could not be read") from exc
    try:
        sheets: dict[str, Grid] = {}
        for ws in wb.worksheets:
            grid: Grid = []
            for row in ws.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLUMNS, values_only=True):
                grid.append([_cell_text(value) for value in row])
            sheets[ws.title] = _trim(grid)
    finally:
        wb.close()
    if not any(sheets.values()):
        raise ValidationFailedError("The workbook has no data")
    return Workbook(sheets=sheets)


def _read_delimited(data: bytes, *, tab: bool) -> Grid:
    text = _decode(data)
    delimiter = "\t" if tab else _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    grid: Grid = []
    for index, row in enumerate(reader):
        if index >= MAX_ROWS:
            break
        grid.append([_cell_text(value) for value in row[:MAX_COLUMNS]])
    grid = _trim(grid)
    if not grid:
        raise ValidationFailedError("The file has no data")
    return grid


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnsupportedFileError("Text file encoding not recognised; save it as UTF-8")


def _sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _cell_text(value: object) -> Cell:
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else format(Decimal(repr(value)), "f")
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _trim(grid: Grid) -> Grid:
    while grid and not any(grid[-1]):
        grid.pop()
    width = max((i + 1 for row in grid for i, v in enumerate(row) if v is not None), default=0)
    return [row[:width] + [None] * (width - len(row[:width])) for row in grid]
