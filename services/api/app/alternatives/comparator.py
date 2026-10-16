"""Parameter-by-parameter comparison of a candidate part against the original, and the
resulting fit class. Deterministic and explainable: every verdict names the parameters
that drove it.

Each compared attribute has a rule:
  exact      candidate must equal the original (e.g. resistance, gain)
  min        candidate must be ≥ original (ratings: voltage, current, flash)
  max        candidate must be ≤ original (tolerance)
  temp_min   candidate's lower temperature limit must be ≤ original's
  temp_max   candidate's upper temperature limit must be ≥ original's
and an effect when violated:
  unsuitable  electrically incompatible → NOT_SUITABLE
  review      fits electrically but needs a layout/firmware/design review → FUNCTIONAL
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

from app.domain.enums import CompareResult, FitClass, Lifecycle
from app.domain.models import AttrCompare

Kind = Literal["exact", "min", "max", "temp_min", "temp_max"]
Effect = Literal["unsuitable", "review"]


@dataclass(frozen=True, slots=True)
class AttrRule:
    name: str
    kind: Kind
    effect: Effect = "unsuitable"


PACKAGE = AttrRule("package", "exact", "review")
TEMPERATURE = (AttrRule("temp_min_c", "temp_min"), AttrRule("temp_max_c", "temp_max"))

RULES_BY_CATEGORY: dict[str, tuple[AttrRule, ...]] = {
    "resistor": (
        AttrRule("resistance_ohm", "exact"),
        AttrRule("tolerance_pct", "max"),
        AttrRule("power_w", "min"),
        PACKAGE,
    ),
    "capacitor": (
        AttrRule("capacitance_f", "exact"),
        AttrRule("voltage_v", "min"),
        AttrRule("dielectric", "exact", "review"),
        PACKAGE,
    ),
    "inductor": (AttrRule("inductance_h", "exact"), AttrRule("isat_a", "min"), PACKAGE),
    "hall_sensor": (
        AttrRule("function", "exact"),
        AttrRule("output", "exact"),
        AttrRule("vcc_max_v", "min"),
        PACKAGE,
        *TEMPERATURE,
    ),
    "can_transceiver": (
        AttrRule("standard", "exact"),
        AttrRule("max_rate_kbps", "min"),
        PACKAGE,
        *TEMPERATURE,
    ),
    "mcu": (
        AttrRule("core", "exact"),
        AttrRule("flash_kb", "min"),
        AttrRule("pins", "exact", "review"),
        PACKAGE,
        *TEMPERATURE,
    ),
    "gate_driver": (
        AttrRule("function", "exact"),
        AttrRule("interface", "exact", "review"),
        AttrRule("vm_max_v", "min"),
        PACKAGE,
        *TEMPERATURE,
    ),
    "current_sense": (
        AttrRule("gain_v_per_v", "exact"),
        AttrRule("cm_max_v", "min"),
        PACKAGE,
        *TEMPERATURE,
    ),
}
DEFAULT_RULES: tuple[AttrRule, ...] = (PACKAGE,)

_ENDING = {Lifecycle.EOL, Lifecycle.OBSOLETE}


def _value(params: dict[str, JsonValue], package: str | None, name: str) -> JsonValue:
    if name == "package":
        return params.get("package", package)
    return params.get(name)


def _text(value: JsonValue) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _judge(rule: AttrRule, original: JsonValue, candidate: JsonValue) -> CompareResult:
    if original is None or candidate is None:
        return CompareResult.UNKNOWN
    if (
        rule.kind == "exact"
        or not isinstance(original, int | float)
        or not isinstance(candidate, int | float)
    ):
        same = str(original).strip().casefold() == str(candidate).strip().casefold()
        return CompareResult.MATCH if same else CompareResult.MISMATCH
    if original == candidate:
        return CompareResult.MATCH
    better = {
        "min": candidate > original,
        "max": candidate < original,
        "temp_min": candidate < original,
        "temp_max": candidate > original,
    }[rule.kind]
    return CompareResult.WITHIN_TOLERANCE if better else CompareResult.MISMATCH


def compare(
    category: str | None,
    original_params: dict[str, JsonValue],
    original_package: str | None,
    candidate_params: dict[str, JsonValue],
    candidate_package: str | None,
) -> list[AttrCompare]:
    rules = RULES_BY_CATEGORY.get(category or "", DEFAULT_RULES)
    return [
        AttrCompare(
            attribute=rule.name,
            original=_text(_value(original_params, original_package, rule.name)),
            candidate=_text(_value(candidate_params, candidate_package, rule.name)),
            critical=rule.effect == "unsuitable",
            result=_judge(
                rule,
                _value(original_params, original_package, rule.name),
                _value(candidate_params, candidate_package, rule.name),
            ),
        )
        for rule in rules
    ]


def classify(
    comparison: list[AttrCompare], relation: str, candidate_lifecycle: Lifecycle
) -> tuple[FitClass, list[str]]:
    """Fit class plus the reasons that decided it."""
    if candidate_lifecycle in _ENDING:
        return FitClass.NOT_SUITABLE, [f"Candidate is itself {candidate_lifecycle.value.lower()}"]
    blocking = [c for c in comparison if c.critical and c.result is CompareResult.MISMATCH]
    if blocking:
        return FitClass.NOT_SUITABLE, [
            f"{c.attribute}: {c.candidate} vs required {c.original}" for c in blocking
        ]
    review = [c for c in comparison if not c.critical and c.result is CompareResult.MISMATCH]
    unknown = [c for c in comparison if c.critical and c.result is CompareResult.UNKNOWN]
    reasons = [
        f"{c.attribute} differs ({c.original} → {c.candidate}): needs design review" for c in review
    ]
    reasons += [f"{c.attribute} not published for both parts: verify" for c in unknown]
    if relation == "FUNCTIONAL":
        reasons.append("Catalog cross-reference marks it as a functional (not drop-in) equivalent")
    if reasons:
        return FitClass.FUNCTIONAL, reasons
    improved = [c.attribute for c in comparison if c.result is CompareResult.WITHIN_TOLERANCE]
    note = f"; better {', '.join(improved)}" if improved else ""
    return FitClass.DROP_IN, [f"All critical parameters match and the footprint is the same{note}"]
