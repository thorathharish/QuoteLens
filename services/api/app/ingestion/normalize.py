"""Value normalization for parsed BOM cells. Pure functions, no I/O."""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_REFDES_EXPANSION = 1_000

# ── Manufacturer names ───────────────────────────────────────

_CANONICAL_MANUFACTURERS: dict[str, tuple[str, ...]] = {
    "Texas Instruments": ("ti", "t i", "texas instruments", "texas"),
    "STMicroelectronics": (
        "st",
        "st micro",
        "stmicro",
        "stmicroelectronics",
        "st microelectronics",
    ),
    "Microchip Technology": ("microchip", "microchip tech", "mchp", "atmel"),
    "NXP Semiconductors": ("nxp", "nxp semiconductors", "freescale"),
    "Nexperia": ("nexperia", "nxp nexperia"),
    "Allegro MicroSystems": ("allegro", "allegro microsystems"),
    "Infineon Technologies": ("infineon", "infineon technologies", "international rectifier"),
    "Analog Devices": ("analog devices", "adi", "linear technology", "maxim integrated", "maxim"),
    "onsemi": ("onsemi", "on semi", "on semiconductor", "fairchild"),
    "Diodes Incorporated": ("diodes", "diodes inc", "diodes incorporated"),
    "Vishay": ("vishay", "vishay dale", "vishay siliconix", "vishay general semiconductor"),
    "Littelfuse": ("littelfuse", "littlefuse"),
    "Lite-On": ("lite on", "liteon", "lite on inc"),
    "Yageo": ("yageo",),
    "Panasonic": ("panasonic", "panasonic electronic components"),
    "Murata": ("murata", "murata electronics", "murata manufacturing"),
    "Samsung Electro-Mechanics": ("samsung", "samsung electro mechanics", "semco"),
    "KEMET": ("kemet",),
    "Bourns": ("bourns",),
    "Würth Elektronik": ("wurth", "wurth elektronik", "wurth electronics", "we"),
    "Abracon": ("abracon",),
    "Molex": ("molex",),
    "TE Connectivity": ("te", "te connectivity", "tyco", "tyco electronics"),
    "Espressif Systems": ("espressif", "espressif systems"),
    "Bosch Sensortec": ("bosch", "bosch sensortec"),
    "GCT": ("gct", "global connector technology"),
    "JST": ("jst",),
    "Coilcraft": ("coilcraft",),
}
_SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "ltd",
    "llc",
    "gmbh",
    "ag",
    "sa",
    "plc",
    "technology",
    "technologies",
    "semiconductor",
    "semiconductors",
}
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _manufacturer_key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    words = _NON_ALNUM.sub(" ", folded).split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


_MANUFACTURER_INDEX: dict[str, str] = {
    _manufacturer_key(alias): canonical
    for canonical, aliases in _CANONICAL_MANUFACTURERS.items()
    for alias in (*aliases, canonical)
}


def normalize_manufacturer(raw: str | None) -> str | None:
    """Canonical name for known manufacturers; otherwise the trimmed input (never guessed)."""
    if raw is None or not raw.strip():
        return None
    key = _manufacturer_key(raw)
    if key in _MANUFACTURER_INDEX:
        return _MANUFACTURER_INDEX[key]
    # Distributors add a region, division or product line after the maker's name ("Nexperia
    # USA Inc.", "Panasonic Industry", "TE Connectivity ALCOSWITCH Switches"): the longest
    # known name the key starts with wins. Two-letter aliases ("st", "te") must match whole.
    words = key.split()
    for n in range(len(words) - 1, 0, -1):
        prefix = " ".join(words[:n])
        if len(prefix.replace(" ", "")) >= 3 and prefix in _MANUFACTURER_INDEX:
            return _MANUFACTURER_INDEX[prefix]
    return " ".join(raw.split())


# ── Quantity and unit of measure ─────────────────────────────

_QTY = re.compile(
    r"^\s*([0-9][0-9,]*(?:\.[0-9]+)?|\.[0-9]+)\s*(?:pcs?|nos?|ea|each|units?)?\s*$", re.IGNORECASE
)

_UOM: dict[str, str] = {
    "": "EA",
    "EA": "EA",
    "EACH": "EA",
    "PC": "EA",
    "PCS": "EA",
    "PCE": "EA",
    "NOS": "EA",
    "NO": "EA",
    "NUMBER": "EA",
    "UNIT": "EA",
    "UNITS": "EA",
    "QTY": "EA",
    "M": "M",
    "METER": "M",
    "METRE": "M",
    "METERS": "M",
    "MM": "MM",
    "CM": "CM",
    "FT": "FT",
    "FEET": "FT",
    "IN": "IN",
    "INCH": "IN",
    "KG": "KG",
    "G": "G",
    "L": "L",
    "ML": "ML",
}


@dataclass(frozen=True, slots=True)
class ParsedQuantity:
    value: Decimal | None
    error: str | None = None


def parse_quantity(raw: str | None) -> ParsedQuantity:
    if raw is None or not raw.strip():
        return ParsedQuantity(None, "Quantity is empty")
    match = _QTY.match(raw)
    if not match:
        return ParsedQuantity(None, f"Quantity '{raw}' is not a number")
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return ParsedQuantity(None, f"Quantity '{raw}' is not a number")
    if value <= 0:
        return ParsedQuantity(None, f"Quantity must be greater than zero (got {raw})")
    return ParsedQuantity(Decimal(int(value)) if value == value.to_integral() else value)


def normalize_uom(raw: str | None) -> str:
    key = (raw or "").strip().upper().rstrip(".")
    return _UOM.get(key, key)


# ── Reference designators ────────────────────────────────────

_SPLIT = re.compile(r"[,;\s]+")
_RANGE = re.compile(r"^([A-Z]+)(\d+)\s*-\s*(?:([A-Z]+))?(\d+)$", re.IGNORECASE)


def expand_refdes(raw: str | None) -> list[str]:
    """'R1-R4, C7' → ['R1', 'R2', 'R3', 'R4', 'C7']. Unrecognized tokens are kept as-is."""
    if raw is None:
        return []
    designators: list[str] = []
    for token in _SPLIT.split(_join_spaced_ranges(raw.strip())):
        if not token:
            continue
        match = _RANGE.match(token)
        if match:
            prefix, start, end_prefix, end = match.groups()
            lo, hi = int(start), int(end)
            same_prefix = end_prefix is None or end_prefix.upper() == prefix.upper()
            if same_prefix and lo <= hi and hi - lo < MAX_REFDES_EXPANSION:
                designators.extend(f"{prefix.upper()}{n}" for n in range(lo, hi + 1))
                continue
        designators.append(token.upper())
    return designators


def _join_spaced_ranges(text: str) -> str:
    return re.sub(r"\s*-\s*", "-", text)


# ── Flags ────────────────────────────────────────────────────

_TRUE = {"y", "yes", "true", "1", "x", "dnp", "dnf", "nf", "nc", "not fitted", "do not fit"}
_FALSE = {"n", "no", "false", "0", "fit", "fitted", "f"}


def parse_fitted(raw: str | None) -> bool | None:
    """For "Fitted"/"Populate" columns: True means the part IS fitted."""
    if raw is not None and raw.strip().casefold() in _TRUE - {"y", "yes", "true", "1", "x"}:
        return False  # textual DNP markers such as "not fitted" or "DNP"
    return parse_flag(raw)


def parse_flag(raw: str | None) -> bool | None:
    """True/False for recognised yes/no markers, None when empty or unrecognised."""
    if raw is None:
        return None
    key = raw.strip().casefold()
    if key in _TRUE:
        return True
    if key in _FALSE:
        return False
    return None


def parse_price(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[^0-9.]", "", raw)
    try:
        value = Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None
    return value if value is not None and value > 0 else None
