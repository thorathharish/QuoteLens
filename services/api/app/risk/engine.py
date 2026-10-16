"""Evaluate the rule catalog over a BOM and summarize readiness. Pure: no I/O."""

from collections import Counter
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import RiskStatus, Severity
from app.domain.facts import Fact, calculated, unavailable
from app.domain.models import BomLine, Component, LineImpact, Offer, Project, Risk
from app.risk.context import RiskContext
from app.risk.rules import RULES

UNRESOLVED = frozenset({RiskStatus.OPEN, RiskStatus.ACKNOWLEDGED})
SERIOUS = frozenset({Severity.BLOCKER, Severity.HIGH})
_SEVERITY_ORDER = {Severity.BLOCKER: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}


def evaluate(
    project: Project,
    lines: Sequence[BomLine],
    offers_by_line: dict[str, list[Offer]],
    components: dict[str, Component],
    impacts: dict[str, LineImpact],
    material_total: Decimal | None,
    today: date,
) -> list[Risk]:
    risks: list[Risk] = []
    for line in lines:
        if line.dnp:
            continue
        offers = offers_by_line.get(line.id, [])
        ctx = RiskContext(
            project=project,
            line=line,
            component=components.get(line.match.component_id or ""),
            offers=offers,
            selected=next((o for o in offers if o.id == line.selected_offer_id), None),
            impact=impacts.get(line.id),
            material_total=material_total,
            today=today,
        )
        risks.extend(risk for rule in RULES if (risk := rule(ctx)) is not None)
    return sort_risks(risks)


def sort_risks(risks: Sequence[Risk]) -> list[Risk]:
    def exposure(risk: Risk) -> Decimal:
        return (
            risk.cost_exposure.value
            if risk.cost_exposure and risk.cost_exposure.value
            else Decimal(0)
        )

    return sorted(risks, key=lambda r: (_SEVERITY_ORDER[r.severity], -exposure(r), r.id))


def carry_decisions(new: Sequence[Risk], previous: Sequence[Risk]) -> list[Risk]:
    """Keep the user's review status for risks that still apply after a re-run."""
    decided = {r.id: r for r in previous if r.status is not RiskStatus.OPEN}
    return [
        risk.model_copy(
            update={
                "status": decided[risk.id].status,
                "resolution_note": decided[risk.id].resolution_note,
            }
        )
        if risk.id in decided
        else risk
        for risk in new
    ]


class RiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    by_severity: dict[Severity, int]
    by_category: dict[str, int]
    unresolved_by_severity: dict[Severity, int]
    open_blockers: int
    ready: bool
    readiness_pct: Fact[Decimal]
    spend_at_risk_pct: Fact[Decimal]
    top_exposure: list[str]


def summarize(
    risks: Sequence[Risk],
    costed_lines: int,
    line_costs: dict[str, Decimal],
    material: Decimal | None,
) -> RiskSummary:
    unresolved = [r for r in risks if r.status in UNRESOLVED]
    blockers = [r for r in unresolved if r.severity is Severity.BLOCKER]
    serious_lines = {r.line_id for r in unresolved if r.severity in SERIOUS and r.line_id}

    if costed_lines:
        clean = costed_lines - len(serious_lines)
        readiness = calculated(
            (Decimal(clean) / costed_lines).quantize(Decimal("0.001"), ROUND_HALF_UP),
            f"{clean} of {costed_lines} lines without unresolved blocker/high risks",
        )
    else:
        readiness = unavailable("No BOM lines")

    if material:
        at_risk = sum(
            (line_costs.get(line_id, Decimal(0)) for line_id in serious_lines), Decimal(0)
        )
        spend = calculated(
            (at_risk / material).quantize(Decimal("0.001"), ROUND_HALF_UP),
            f"cost of lines with unresolved blocker/high risks ÷ material total "
            f"({at_risk:.2f} ÷ {material:.2f})",
        )
    else:
        spend = unavailable("Material cost unavailable")

    return RiskSummary(
        total=len(risks),
        by_severity=dict(Counter(r.severity for r in risks)),
        by_category=dict(Counter(r.category.value for r in risks)),
        unresolved_by_severity=dict(Counter(r.severity for r in unresolved)),
        open_blockers=len(blockers),
        ready=not blockers,
        readiness_pct=readiness,
        spend_at_risk_pct=spend,
        top_exposure=[r.id for r in sort_risks([r for r in unresolved if r.cost_exposure])][:5],
    )
