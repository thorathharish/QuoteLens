"""Merge duplicate BOM lines for the same part.

Lines merge only when MPN, DNP state and unit of measure agree and the manufacturers do
not contradict each other. Anything else is kept separate and flagged, never merged
silently. Merged quantities become CALCULATED facts that cite every source row.
"""

from collections import defaultdict
from decimal import Decimal

from app.domain.enums import IssueCode
from app.domain.facts import calculated
from app.domain.models import BomLine, Issue


def consolidate(lines: list[BomLine]) -> list[BomLine]:
    groups: dict[tuple[str, bool], list[BomLine]] = defaultdict(list)
    for line in lines:
        if line.mpn is not None:
            groups[(line.mpn, line.dnp)].append(line)

    merged_away: set[str] = set()
    replacements: dict[str, BomLine] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        uoms = {line.uom for line in group}
        manufacturers = {line.manufacturer for line in group if line.manufacturer}
        if len(uoms) > 1:
            _flag(
                group,
                replacements,
                IssueCode.UOM_CONFLICT,
                f"Same part listed with different units: {', '.join(sorted(uoms))}",
            )
        elif len(manufacturers) > 1:
            _flag(
                group,
                replacements,
                IssueCode.DUPLICATE_MPN_CONFLICT,
                f"Same MPN listed with different manufacturers: {', '.join(sorted(manufacturers))}",
            )
        elif all(line.qty_per.is_available for line in group):
            first, *rest = group
            replacements[first.id] = _merge(first, rest)
            merged_away.update(line.id for line in rest)
        # Lines with invalid quantities stay separate; their QTY_INVALID issue is reported.

    return [replacements.get(line.id, line) for line in lines if line.id not in merged_away]


def _merge(first: BomLine, rest: list[BomLine]) -> BomLine:
    group = [first, *rest]
    quantities = [line.qty_per.value for line in group]
    total = sum((q for q in quantities if q is not None), Decimal(0))
    rows = [row for line in group for row in line.source_rows]
    evidence = tuple(e for line in group for e in line.qty_per.evidence_ids)
    formula = " + ".join(str(q) for q in quantities) + f" (rows {', '.join(map(str, rows))})"
    return first.model_copy(
        update={
            "qty_per": calculated(total, formula, *evidence),
            "refdes": [d for line in group for d in line.refdes],
            "source_rows": rows,
            "manufacturer": first.manufacturer
            or next((x.manufacturer for x in rest if x.manufacturer), None),
        }
    )


def _flag(group: list[BomLine], out: dict[str, BomLine], code: IssueCode, message: str) -> None:
    for line in group:
        current = out.get(line.id, line)
        out[line.id] = current.model_copy(
            update={"validation": [*current.validation, Issue(code=code, message=message)]}
        )
