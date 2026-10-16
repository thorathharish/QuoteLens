"""Golden tests: the Phase 1 sample BOMs parse into the lines and issues their manifests seed."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.enums import BomField, IssueCode, Provenance
from app.domain.models import BomLine
from app.ingestion.column_mapper import propose_mapping
from app.ingestion.header_detect import detect_header
from app.ingestion.parse import parse_rows
from app.ingestion.readers import read_bom_file

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"


async def _parse(name: str) -> tuple[list[BomLine], dict[str, Any], dict[BomField, str]]:
    data = (SAMPLES / name).read_bytes()
    workbook = read_bom_file(name, data, 5 * 1_048_576)
    location = detect_header(workbook)
    grid = workbook.sheets[location.sheet]
    mapping, _ = await propose_mapping(
        grid[location.row_index], grid[location.row_index + 1 :], None
    )
    parsed = parse_rows(grid, location.row_index, mapping, filename=name, sheet=location.sheet)
    manifest = json.loads(
        (SAMPLES / name.rsplit(".", 1)[0]).with_suffix(".expected.json").read_text(encoding="utf-8")
    )
    assert location.row_number == manifest["header_row"]
    if manifest["sheet"]:
        assert location.sheet == manifest["sheet"]
    fields = {m.field: m.header for m in mapping if m.field is not None}
    return parsed.lines, manifest, fields


def _line_for(lines: list[BomLine], spreadsheet_row: int) -> BomLine:
    return next(line for line in lines if spreadsheet_row in line.source_rows)


@pytest.mark.parametrize("name", ["motor_controller.xlsx", "iot_sensor.csv", "messy_format.xlsx"])
async def test_sample_parses_to_expected_lines_and_issues(name: str) -> None:
    lines, manifest, fields = await _parse(name)
    assert {BomField.MPN, BomField.MANUFACTURER, BomField.QTY_PER, BomField.REFDES} <= set(fields)
    assert len(lines) == manifest["lines_after_consolidation"]

    seeded = {row["row"]: row for row in manifest["seeded_rows"]}
    for data_row in range(1, manifest["data_rows"] + 1):
        line = _line_for(lines, manifest["header_row"] + data_row)
        codes = {issue.code.value for issue in line.validation}
        expected = set(seeded.get(data_row, {}).get("issues", []))
        assert expected <= codes, f"{name} row {data_row}: expected {expected}, got {codes}"
        if data_row not in seeded:
            assert not codes, f"{name} row {data_row} ({line.mpn}) should be clean: {codes}"


async def test_motor_controller_consolidation_and_provenance() -> None:
    lines, _, _ = await _parse("motor_controller.xlsx")
    caps = [line for line in lines if line.mpn == "GRM188R71H104KA93D"]
    assert len(caps) == 1
    merged = caps[0]
    assert merged.qty_per.value == 24
    assert merged.qty_per.provenance is Provenance.CALCULATED
    assert merged.qty_per.formula is not None
    assert "20 + 4" in merged.qty_per.formula
    assert len(merged.refdes) == 24
    assert len(merged.qty_per.evidence_ids) == 2

    resistors_1k = [line for line in lines if line.mpn == "RC0603FR-071KL"]
    assert sorted(line.dnp for line in resistors_1k) == [False, True]  # DNP never merged

    hall = next(line for line in lines if line.mpn == "A1101ELHLT-T")
    assert hall.manufacturer == "Allegro MicroSystems"
    assert hall.refdes == ["U11", "U12", "U13"]
    assert hall.qty_per.provenance is Provenance.ACTUAL

    tbd = next(line for line in lines if line.mpn == "0430450200")
    assert tbd.qty_per.provenance is Provenance.UNAVAILABLE
    assert "TBD" in (tbd.qty_per.note or "")

    target = next(line for line in lines if line.mpn == "LM5164DDAR")
    assert target.bom_unit_price is not None
    assert str(target.bom_unit_price.value) == "0.95"

    assert [line.line_no for line in lines] == list(range(1, len(lines) + 1))


async def test_messy_format_handles_fitted_flag_and_units() -> None:
    lines, _, fields = await _parse("messy_format.xlsx")
    assert fields[BomField.FITTED] == "Fitted (Y/N)"
    assert fields[BomField.UOM] == "Unit"
    debug_resistor = next(line for line in lines if line.cpn == "DIB-2003")
    assert debug_resistor.dnp is True
    assert IssueCode.DNP in {i.code for i in debug_resistor.validation}
    assert all(line.uom == "EA" for line in lines)
