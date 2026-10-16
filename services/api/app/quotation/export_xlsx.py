"""Quote workbook: Summary, Lines, Risks, Assumptions. Values keep their provenance in an
adjacent column, and demo-snapshot data is disclosed on the summary sheet."""

import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.enums import DataMode
from app.domain.facts import Fact
from app.domain.models import Project, QuoteVersion, Risk

_HEADER = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
_TITLE = Font(bold=True, size=14)
_MONEY = "#,##0.00"
Cell = str | int | float | None
_UNIT = "#,##0.0000"


def _value(fact: Fact[Decimal] | None) -> float | str:
    if fact is None or fact.value is None:
        return "—"
    return float(fact.value)


def _label(fact: Fact[Decimal] | None) -> str:
    if fact is None:
        return ""
    return fact.provenance.value + (f": {fact.note}" if fact.note else "")


def _header(ws: Worksheet, row: int, titles: list[str]) -> None:
    for col, title in enumerate(titles, start=1):
        cell = ws.cell(row=row, column=col, value=title)
        cell.font, cell.fill = _HEADER, _HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _widths(ws: Worksheet, widths: list[int]) -> None:
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width


def build_workbook(project: Project, quote: QuoteVersion, risks: list[Risk]) -> bytes:
    wb = Workbook()
    summary = wb.active
    assert summary is not None
    summary.title = "Summary"
    summary["A1"] = f"Quotation: {project.name}"
    summary["A1"].font = _TITLE
    rows: list[tuple[str, Cell]] = [
        ("Customer", project.customer or "—"),
        ("Quote version", f"v{quote.version} ({quote.status.value})"),
        ("Created", quote.created_at.strftime("%Y-%m-%d %H:%M UTC")),
        (
            "Finalized",
            quote.finalized_at.strftime("%Y-%m-%d %H:%M UTC") if quote.finalized_at else "—",
        ),
        ("Currency", quote.currency),
        (
            "Ready to quote",
            "Yes"
            if quote.readiness.ready
            else f"No: {len(quote.readiness.open_blockers)} open blocker(s)",
        ),
        ("Waived risks", len(quote.readiness.waived)),
        ("Unpriced lines", quote.unpriced_lines),
        ("Note", quote.note or "—"),
    ]
    for offset, (key, value) in enumerate(rows, start=3):
        summary.cell(row=offset, column=1, value=key).font = Font(bold=True)
        summary.cell(row=offset, column=2, value=value)
    disclaimer_row = 3 + len(rows) + 1
    summary.cell(
        row=disclaimer_row,
        column=1,
        value="Pricing data: "
        + {
            DataMode.DEMO_SNAPSHOT: "DEMO SNAPSHOT (synthetic, for demonstration only)",
            DataMode.CACHE_FIRST: "cached distributor data (see each line's source and date)",
            DataMode.LIVE_FIRST: "live distributor data at analysis time",
        }[quote.data_mode],
    ).font = Font(italic=True)

    start = disclaimer_row + 2
    _header(
        summary, start, ["Build quantity", "Material", "Adders", "Total", "Per unit", "Provenance"]
    )
    for i, v in enumerate(quote.volumes, start=start + 1):
        summary.cell(row=i, column=1, value=v.volume)
        for col, fact in ((2, v.material), (3, v.adders), (4, v.total), (5, v.per_unit)):
            cell = summary.cell(row=i, column=col, value=_value(fact))
            cell.number_format = _UNIT if col == 5 else _MONEY
        summary.cell(row=i, column=6, value=_label(v.total))
    _widths(summary, [22, 18, 16, 18, 14, 60])

    lines = wb.create_sheet("Lines")
    primary = quote.volumes[0].volume if quote.volumes else 0
    _header(
        lines,
        1,
        [
            "#",
            "CPN",
            "MPN",
            "Manufacturer",
            "Description",
            "Qty/assy",
            "Ref des",
            "DNP",
            "Substituted from",
            "Distributor",
            f"Unit price @ {primary}",
            "Price provenance",
            f"Extended @ {primary}",
            "Extended provenance",
        ],
    )
    for r, line in enumerate(quote.lines, start=2):
        values: list[Cell] = [
            line.line_no,
            line.cpn,
            line.mpn or "—",
            line.manufacturer,
            line.description,
            _value(line.qty_per),
            ",".join(line.refdes),
            "Yes" if line.dnp else "",
            line.substituted_from or "",
            line.distributor or "—",
            _value(line.unit_price),
            _label(line.unit_price),
            _value(line.extended),
            _label(line.extended),
        ]
        for c, value in enumerate(values, start=1):
            lines.cell(row=r, column=c, value=value)
        lines.cell(row=r, column=11).number_format = _UNIT
        lines.cell(row=r, column=13).number_format = _MONEY
    lines.freeze_panes = "A2"
    _widths(lines, [5, 12, 22, 22, 30, 9, 18, 6, 18, 12, 14, 30, 14, 40])

    risk_ws = wb.create_sheet("Risks")
    _header(
        risk_ws, 1, ["Severity", "Rule", "Category", "Title", "Why", "Status", "Resolution note"]
    )
    for r, risk in enumerate(risks, start=2):
        for c, value in enumerate(
            [
                risk.severity.value,
                risk.rule_id,
                risk.category.value,
                risk.title,
                risk.why,
                risk.status.value,
                risk.resolution_note or "",
            ],
            start=1,
        ):
            cell = risk_ws.cell(row=r, column=c, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    _widths(risk_ws, [10, 7, 11, 30, 90, 13, 40])

    assumptions = wb.create_sheet("Assumptions")
    a = quote.assumptions
    entries: list[tuple[str, Cell]] = [
        ("Scrap policy", a.scrap_policy.mode),
        (
            "Fixed scrap %",
            float(a.scrap_policy.fixed_pct) if a.scrap_policy.fixed_pct is not None else "—",
        ),
        *[(f"Scrap tier ≥ {t.min_unit_price}", float(t.scrap_pct)) for t in a.scrap_policy.tiers],
        *[(f"FX {k}", float(v)) for k, v in a.fx_overrides.items()],
        (
            "Assembly per unit",
            float(a.adders.assembly_per_unit) if a.adders.assembly_per_unit else "—",
        ),
        ("NRE", float(a.adders.nre) if a.adders.nre else "—"),
        ("Overhead %", float(a.adders.overhead_pct) if a.adders.overhead_pct else "—"),
        ("Margin %", float(a.adders.margin_pct) if a.adders.margin_pct else "—"),
    ]
    _header(assumptions, 1, ["Assumption", "Value"])
    for r, (key, value) in enumerate(entries, start=2):
        assumptions.cell(row=r, column=1, value=key)
        assumptions.cell(row=r, column=2, value=value)
    _widths(assumptions, [28, 16])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
