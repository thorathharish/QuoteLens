"""Scrap / attrition allowance per line. Always an ASSUMED fact that says where it came from.

Modes (Project.assumptions.scrap_policy.mode):
- price_tier (default): cheaper parts get a larger allowance (tiers are user-editable).
- package: an attrition table by package size (written for QuoteLens; small passives lose
  more parts on pick-and-place than large ICs).
- fixed: one percentage for every line.
A per-line override (what-if simulation) always wins.
"""

from decimal import Decimal

from app.domain.facts import Fact, assumed
from app.domain.models import BomLine, ScrapPolicy

_PACKAGE_ATTRITION: dict[str, Decimal] = {
    "0201": Decimal("0.05"),
    "0402": Decimal("0.03"),
    "0603": Decimal("0.02"),
    "0805": Decimal("0.015"),
    "1206": Decimal("0.01"),
    "1210": Decimal("0.01"),
    "2512": Decimal("0.01"),
}
_PACKAGE_DEFAULT = Decimal("0.005")  # ICs, modules, connectors: low attrition


def scrap_allowance(
    line: BomLine,
    policy: ScrapPolicy,
    unit_price: Decimal | None,
    override: Decimal | None = None,
) -> Fact[Decimal]:
    if override is not None:
        return assumed(override, f"What-if override: {override:.1%}")
    if policy.mode == "fixed" and policy.fixed_pct is not None:
        return assumed(policy.fixed_pct, f"Fixed scrap allowance {policy.fixed_pct:.1%}")
    if policy.mode == "package":
        package = (line.package or "").upper()
        for size, pct in _PACKAGE_ATTRITION.items():
            if size in package:
                return assumed(pct, f"Package attrition for {size}: {pct:.1%}")
        return assumed(_PACKAGE_DEFAULT, f"Default package attrition {_PACKAGE_DEFAULT:.1%}")
    if unit_price is None:
        highest = max(policy.tiers, key=lambda t: t.scrap_pct)
        return assumed(
            highest.scrap_pct, f"Price unknown: highest scrap tier {highest.scrap_pct:.1%} applied"
        )
    for tier in sorted(policy.tiers, key=lambda t: t.min_unit_price, reverse=True):
        if unit_price >= tier.min_unit_price:
            return assumed(
                tier.scrap_pct,
                f"Scrap tier for unit price ≥ {tier.min_unit_price}: {tier.scrap_pct:.1%}",
            )
    lowest = min(policy.tiers, key=lambda t: t.min_unit_price)
    return assumed(lowest.scrap_pct, f"Scrap tier {lowest.scrap_pct:.1%}")
