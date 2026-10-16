"""Per-line data validation. Issues are facts about the data; the risk engine (Phase 4)
turns the relevant ones into explained risks."""

import re

from app.domain.enums import IssueCode
from app.domain.models import BomLine, Issue

# Characters seen in real MPNs (incl. "BAT54S,215", "S2B-PH-SM4-TB(LF)(SN)", "0451005.MRL").
_MPN_CHARS = re.compile(r"^[A-Z0-9\-/.,#+()_&]+$")


def validate_line(line: BomLine) -> list[Issue]:
    issues: list[Issue] = []
    if line.dnp:
        issues.append(
            Issue(
                code=IssueCode.DNP,
                field="dnp",
                message="Marked do-not-populate: excluded from cost",
            )
        )

    if line.mpn is None:
        issues.append(
            Issue(
                code=IssueCode.MISSING_MPN,
                field="mpn",
                message="No manufacturer part number; the part cannot be sourced",
            )
        )
    else:
        if line.manufacturer is None:
            issues.append(
                Issue(
                    code=IssueCode.MISSING_MFR,
                    field="manufacturer",
                    message="Manufacturer is empty",
                )
            )
        if len(line.mpn) < 3 or not _MPN_CHARS.match(line.mpn):
            issues.append(
                Issue(
                    code=IssueCode.SUSPECT_MPN_FORMAT,
                    field="mpn",
                    message=f"'{line.mpn_raw}' does not look like a part number",
                )
            )

    qty = line.qty_per
    if not qty.is_available:
        issues.append(
            Issue(
                code=IssueCode.QTY_INVALID,
                field="qty_per",
                message=qty.note or "Quantity is invalid",
            )
        )
    elif qty.value is not None:
        if line.uom == "EA" and qty.value != qty.value.to_integral():
            issues.append(
                Issue(
                    code=IssueCode.QTY_INVALID,
                    field="qty_per",
                    message=f"Quantity {qty.value} must be a whole number for EA",
                )
            )
        elif line.uom == "EA" and line.refdes and len(line.refdes) != qty.value:
            issues.append(
                Issue(
                    code=IssueCode.REFDES_QTY_MISMATCH,
                    field="refdes",
                    message=f"{len(line.refdes)} reference designators but quantity {qty.value}",
                )
            )
    return issues
