"""Header aliases for deterministic column mapping (written for QuoteLens).

Headers and aliases are compared after `normalize_header`, so "Maker Part No." and
"maker part no" are the same. Ambiguous headers such as "Part Number" are deliberately
not listed: the LLM mapper (or the user) decides those from sample values.
"""

import re
import unicodedata

from app.domain.enums import BomField

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_header(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
    return _NON_ALNUM.sub(" ", folded).strip()


_ALIASES: dict[BomField, tuple[str, ...]] = {
    BomField.CPN: (
        "cpn",
        "customer pn",
        "customer p n",
        "customer part number",
        "customer part no",
        "cust pn",
        "cust p n",
        "cust part no",
        "internal pn",
        "internal part number",
    ),
    BomField.MPN: (
        "mpn",
        "mfr pn",
        "mfr p n",
        "mfr part number",
        "mfr part no",
        "mfg pn",
        "mfg p n",
        "mfg part number",
        "manufacturer pn",
        "manufacturer p n",
        "manufacturer part number",
        "manufacturer part no",
        "maker part no",
        "maker pn",
        "maker part number",
        "manufacturer part",
        "mfr part",
    ),
    BomField.MANUFACTURER: (
        "manufacturer",
        "manufacturer name",
        "mfr",
        "mfg",
        "mfr name",
        "make",
        "maker",
        "brand",
    ),
    BomField.DESCRIPTION: (
        "description",
        "desc",
        "part description",
        "item description",
        "component description",
    ),
    BomField.QTY_PER: (
        "qty",
        "quantity",
        "qty per",
        "qty per assy",
        "qty assy",
        "qty per board",
        "qty board",
        "qty per unit",
        "quantity per",
        "quantity per assembly",
        "usage",
        "qty pcb",
    ),
    BomField.UOM: ("uom", "unit", "units", "unit of measure"),
    BomField.REFDES: (
        "ref des",
        "refdes",
        "reference",
        "references",
        "designator",
        "designators",
        "reference designator",
        "reference designators",
        "ref",
        "location",
        "locations",
    ),
    BomField.DNP: (
        "dnp",
        "dnf",
        "do not populate",
        "do not place",
        "do not fit",
        "not fitted",
        "no fit",
    ),
    BomField.FITTED: (
        "fitted",
        "fitted y n",
        "fit",
        "populate",
        "populated",
        "assembled",
        "mount",
        "mounted",
    ),
    BomField.UNIT_PRICE: (
        "unit price",
        "price",
        "target price",
        "target price usd",
        "unit cost",
        "cost",
        "target unit price",
    ),
    BomField.PACKAGE: ("package", "footprint", "case", "package case", "pkg"),
    BomField.VALUE: ("value", "val"),
    BomField.NOTES: ("notes", "note", "remarks", "remark", "comments"),
}

ALIAS_TO_FIELD: dict[str, BomField] = {
    normalize_header(alias): field for field, aliases in _ALIASES.items() for alias in aliases
}

REQUIRED_FIELDS: frozenset[BomField] = frozenset({BomField.QTY_PER})
"""Plus at least one of MPN or DESCRIPTION (checked in `missing_required_fields`)."""


def missing_required_fields(mapped: set[BomField]) -> list[str]:
    missing = [field.value for field in REQUIRED_FIELDS if field not in mapped]
    if BomField.MPN not in mapped and BomField.DESCRIPTION not in mapped:
        missing.append("mpn or description")
    return missing
