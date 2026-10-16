"""Turn mapped spreadsheet rows into BOM lines with BOM-cell evidence.

Ids are derived from the source row number, so re-running a job (Pub/Sub redelivery) or
re-confirming the same mapping overwrites documents instead of duplicating them. Evidence
is one record per row (not per cell) to keep Firestore writes inside the free tier.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter
from pydantic import JsonValue

from app.domain.enums import BomField, EvidenceKind
from app.domain.facts import Evidence, actual, unavailable
from app.domain.models import BomLine, ColumnMapping
from app.domain.mpn import normalize_mpn
from app.ingestion.consolidate import consolidate
from app.ingestion.normalize import (
    expand_refdes,
    normalize_manufacturer,
    normalize_uom,
    parse_fitted,
    parse_flag,
    parse_price,
    parse_quantity,
)
from app.ingestion.readers import Grid
from app.ingestion.validate import validate_line

CellGetter = Callable[[BomField], str | None]


@dataclass(slots=True)
class ParsedBom:
    lines: list[BomLine]
    evidence: list[Evidence]
    skipped_rows: int = 0
    warnings: list[str] = field(default_factory=list)


def line_id(row_number: int) -> str:
    return f"ln_r{row_number:05d}"


def evidence_id(row_number: int) -> str:
    return f"ev_bom_r{row_number:05d}"


def parse_rows(
    grid: Grid,
    header_index: int,
    mapping: list[ColumnMapping],
    *,
    filename: str,
    sheet: str,
) -> ParsedBom:
    columns = {m.field: m for m in mapping if m.field is not None}
    width = max((m.column_index for m in mapping), default=0) + 1
    last_column = get_column_letter(width)

    lines: list[BomLine] = []
    evidence: list[Evidence] = []
    skipped = 0
    for index in range(header_index + 1, len(grid)):
        row = grid[index]
        row_number = index + 1

        def cell(f: BomField, row: list[str | None] = row) -> str | None:
            m = columns.get(f)
            return row[m.column_index] if m is not None and m.column_index < len(row) else None

        if not any(cell(f) for f in columns):
            skipped += 1
            continue

        ev = Evidence(
            id=evidence_id(row_number),
            kind=EvidenceKind.BOM_CELL,
            source_name=filename,
            source_ref=f"{sheet}!A{row_number}:{last_column}{row_number}",
            payload_excerpt=_excerpt(row, mapping),
        )
        evidence.append(ev)
        lines.append(_line(row_number, cell, ev.id))

    consolidated = consolidate(lines)
    validated = [
        line.model_copy(update={"validation": [*line.validation, *validate_line(line)]})
        for line in consolidated
    ]
    for line_no, line in enumerate(validated, start=1):
        line.line_no = line_no
    return ParsedBom(lines=validated, evidence=evidence, skipped_rows=skipped)


def _line(row_number: int, cell: CellGetter, ev_id: str) -> BomLine:
    quantity = parse_quantity(cell(BomField.QTY_PER))
    price = parse_price(cell(BomField.UNIT_PRICE))
    dnp = parse_flag(cell(BomField.DNP))
    fitted = parse_fitted(cell(BomField.FITTED))
    description = cell(BomField.DESCRIPTION) or cell(BomField.VALUE)
    mpn_raw = cell(BomField.MPN)
    manufacturer_raw = cell(BomField.MANUFACTURER)
    return BomLine(
        id=line_id(row_number),
        line_no=1,  # renumbered after consolidation
        cpn=cell(BomField.CPN),
        mpn_raw=mpn_raw,
        mpn=normalize_mpn(mpn_raw),
        manufacturer_raw=manufacturer_raw,
        manufacturer=normalize_manufacturer(manufacturer_raw),
        description=description,
        qty_per=(
            actual(quantity.value, ev_id)
            if quantity.value is not None
            else unavailable(quantity.error or "Quantity is invalid", ev_id)
        ),
        uom=normalize_uom(cell(BomField.UOM)),
        refdes=expand_refdes(cell(BomField.REFDES)),
        dnp=bool(dnp) or fitted is False,
        bom_unit_price=actual(price, ev_id) if price is not None else None,
        package=cell(BomField.PACKAGE),
        source_rows=[row_number],
    )


def _excerpt(row: list[str | None], mapping: list[ColumnMapping]) -> dict[str, JsonValue]:
    return {
        (m.header or f"column {m.column_index + 1}"): row[m.column_index]
        for m in mapping
        if m.column_index < len(row) and row[m.column_index] is not None
    }
