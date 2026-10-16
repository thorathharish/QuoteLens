"""Inputs a risk rule sees for one line, plus helpers to build explained risks."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import JsonValue

from app.domain.enums import ActionType, RiskCategory, Severity
from app.domain.models import Action, BomLine, Component, LineImpact, Offer, Project, Risk
from app.impact.engine import money, num

DEFAULT_HORIZON_DAYS = 84  # used for lead-time risk when no target ship date is set


@dataclass(frozen=True)
class RiskContext:
    project: Project
    line: BomLine
    component: Component | None
    offers: list[Offer]
    selected: Offer | None
    impact: LineImpact | None  # at the primary volume
    material_total: Decimal | None  # BOM material cost at the primary volume
    today: date

    @property
    def volume(self) -> int:
        return self.project.build_quantities[0]

    @property
    def currency(self) -> str:
        return self.project.currency

    @property
    def label(self) -> str:
        refs = self.line.refdes
        where = f"{refs[0]}…{refs[-1]}" if len(refs) > 3 else ",".join(refs)
        return f"{self.line.mpn or self.line.description or 'line'}" + (
            f" ({where})" if where else ""
        )

    @property
    def need(self) -> Decimal | None:
        """Gross quantity needed at the primary volume (scrap included when priced)."""
        if self.impact is not None and self.impact.gross.value is not None:
            return self.impact.gross.value
        qty = self.line.qty_per.value
        return qty * self.volume if qty is not None else None

    @property
    def authorized(self) -> list[Offer]:
        return [o for o in self.offers if o.authorized]

    def bom_evidence(self) -> list[str]:
        return list(self.line.qty_per.evidence_ids)

    def money(self, value: Decimal) -> str:
        return money(value, self.currency)

    def risk(
        self,
        rule_id: str,
        category: RiskCategory,
        severity: Severity,
        title: str,
        why: str,
        *,
        evidence: list[str],
        metrics: dict[str, JsonValue],
        actions: list[tuple[ActionType, str]],
    ) -> Risk:
        evidence_ids = list(dict.fromkeys(e for e in evidence if e)) or self.bom_evidence()
        exposure = (
            self.impact.extended if self.impact and self.impact.extended.is_available else None
        )
        return Risk(
            id=f"rsk_{rule_id.lower()}_{self.line.id}",
            line_id=self.line.id,
            rule_id=rule_id,
            category=category,
            severity=severity,
            title=title,
            why=why,
            metrics=metrics,
            evidence_ids=evidence_ids,
            suggested_actions=[Action(type=t, label=label) for t, label in actions],
            cost_exposure=exposure,
        )


def fmt(value: Decimal | int | None) -> str:
    return "unknown" if value is None else num(value)
