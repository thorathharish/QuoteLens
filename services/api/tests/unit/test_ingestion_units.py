from decimal import Decimal

import pytest

from app.domain.enums import BomField, MappingMethod
from app.domain.errors import FileTooLargeError, UnsupportedFileError, ValidationFailedError
from app.ingestion.column_mapper import ColumnSample, LlmColumnSuggestion, propose_mapping
from app.ingestion.normalize import (
    expand_refdes,
    normalize_manufacturer,
    normalize_uom,
    parse_fitted,
    parse_flag,
    parse_price,
    parse_quantity,
)
from app.ingestion.readers import read_bom_file

MB = 1_048_576


# ── readers ──────────────────────────────────────────────────


def test_csv_with_bom_and_semicolons_is_read() -> None:
    data = "﻿MPN;Qty\nABC-1;2\n".encode()
    sheet = read_bom_file("bom.csv", data, MB).sheets["CSV"]
    assert sheet == [["MPN", "Qty"], ["ABC-1", "2"]]


def test_tsv_and_cp1252_fallback() -> None:
    data = "MPN\tManufacturer\nX1\tW\xfcrth\n".encode("cp1252")
    sheet = read_bom_file("bom.tsv", data, MB).sheets["CSV"]
    assert sheet[1] == ["X1", "Würth"]


@pytest.mark.parametrize(
    ("name", "data", "error"),
    [
        ("bom.xls", b"\xd0\xcf\x11\xe0", UnsupportedFileError),
        ("bom.xlsx", b"not a zip", UnsupportedFileError),
        ("bom.pdf", b"%PDF", UnsupportedFileError),
        ("bom.csv", b"", ValidationFailedError),
        ("bom.csv", b"x" * (MB + 1), FileTooLargeError),
    ],
    ids=["legacy-xls", "fake-xlsx", "pdf", "empty", "too-large"],
)
def test_rejects_bad_files(name: str, data: bytes, error: type[Exception]) -> None:
    with pytest.raises(error):
        read_bom_file(name, data, MB)


# ── normalize ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("2", Decimal(2)),
        ("1,000", Decimal(1000)),
        ("4 pcs", Decimal(4)),
        ("2.0", Decimal(2)),
        ("0.5", Decimal("0.5")),
        ("3 Nos", Decimal(3)),
    ],
)
def test_parse_quantity_valid(raw: str, value: Decimal) -> None:
    parsed = parse_quantity(raw)
    assert parsed.value == value
    assert str(parsed.value) == str(value)  # never exponent notation such as 1E+3


@pytest.mark.parametrize("raw", ["TBD", "", None, "0", "-1", "two"])
def test_parse_quantity_invalid(raw: str | None) -> None:
    parsed = parse_quantity(raw)
    assert parsed.value is None
    assert parsed.error


def test_refdes_expansion() -> None:
    assert expand_refdes("R1-R4, C7") == ["R1", "R2", "R3", "R4", "C7"]
    assert expand_refdes("U11 - U13") == ["U11", "U12", "U13"]
    assert expand_refdes("R5-8") == ["R5", "R6", "R7", "R8"]
    assert expand_refdes("R1-C4") == ["R1-C4"]  # mixed prefixes are left alone
    assert len(expand_refdes("R1-R999999")) == 1  # absurd ranges are not expanded
    assert expand_refdes(None) == []


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("TI", "Texas Instruments"),
        ("T.I.", "Texas Instruments"),
        ("ST Micro", "STMicroelectronics"),
        ("Microchip Tech", "Microchip Technology"),
        ("Wurth Electronics", "Würth Elektronik"),
        ("Würth", "Würth Elektronik"),
        ("Diodes Inc", "Diodes Incorporated"),
        ("Murata Electronics", "Murata"),
        ("NXP/Nexperia", "Nexperia"),
        ("ON Semi", "onsemi"),
        ("Acme Widgets Ltd", "Acme Widgets Ltd"),
        ("", None),
    ],
)
def test_manufacturer_normalization(raw: str, canonical: str | None) -> None:
    assert normalize_manufacturer(raw) == canonical


def test_uom_flags_and_price() -> None:
    assert normalize_uom("Nos") == "EA"
    assert normalize_uom(None) == "EA"
    assert normalize_uom("meter") == "M"
    assert parse_flag("DNP") is True
    assert parse_flag("n") is False
    assert parse_flag("maybe") is None
    assert parse_fitted("Y") is True
    assert parse_fitted("N") is False
    assert parse_fitted("not fitted") is False
    assert parse_price("$1.20") == Decimal("1.20")
    assert parse_price("n/a") is None


# ── column mapping ───────────────────────────────────────────


class FakeMapper:
    def __init__(self, suggestions: list[LlmColumnSuggestion] | Exception) -> None:
        self.suggestions = suggestions
        self.calls: list[list[ColumnSample]] = []

    async def suggest(
        self, columns: list[ColumnSample], available: list[BomField]
    ) -> list[LlmColumnSuggestion]:
        self.calls.append(list(columns))
        if isinstance(self.suggestions, Exception):
            raise self.suggestions
        return self.suggestions


HEADERS = ["Item", "Maker Part No.", "Make", "Qty/Assy", "Bauteil"]
ROWS = [["1", "ABC", "TI", "2", "10k resistor"], ["2", "DEF", "ST", "1", "LDO 3V3"]]


async def test_aliases_map_without_llm() -> None:
    mapping, warnings = await propose_mapping(HEADERS, ROWS, None)
    fields = {m.header: m.field for m in mapping}
    assert fields["Maker Part No."] is BomField.MPN
    assert fields["Make"] is BomField.MANUFACTURER
    assert fields["Qty/Assy"] is BomField.QTY_PER
    assert fields["Bauteil"] is None
    assert warnings == []


async def test_llm_maps_only_unmapped_columns_with_sample_values() -> None:
    mapper = FakeMapper(
        [
            LlmColumnSuggestion(
                column_index=4, field=BomField.DESCRIPTION, confidence=0.9, reason="text"
            ),
            LlmColumnSuggestion(
                column_index=0, field=BomField.MPN, confidence=0.99, reason="taken"
            ),
        ]
    )
    mapping, _ = await propose_mapping(HEADERS, ROWS, mapper)
    assert {c.header for c in mapper.calls[0]} == {"Item", "Bauteil"}
    assert mapper.calls[0][-1].values == ["10k resistor", "LDO 3V3"]
    by_header = {m.header: m for m in mapping}
    assert by_header["Bauteil"].field is BomField.DESCRIPTION
    assert by_header["Bauteil"].method is MappingMethod.LLM
    assert by_header["Item"].field is None  # MPN was already taken by an alias


async def test_low_confidence_llm_suggestions_are_dropped() -> None:
    mapper = FakeMapper(
        [
            LlmColumnSuggestion(
                column_index=4, field=BomField.NOTES, confidence=0.4, reason="guess"
            ),
        ]
    )
    mapping, _ = await propose_mapping(HEADERS, ROWS, mapper)
    assert mapping[4].field is None


async def test_llm_failure_degrades_to_unmapped_with_warning() -> None:
    mapping, warnings = await propose_mapping(HEADERS, ROWS, FakeMapper(TimeoutError()))
    assert mapping[4].field is None
    assert warnings
    assert mapping[1].field is BomField.MPN  # alias results survive
