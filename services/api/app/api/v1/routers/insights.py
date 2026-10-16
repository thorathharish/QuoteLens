"""Overview, assumptions, manufacturing impact and what-if simulation."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import (
    NextAction,
    Overview,
    SimulationRequest,
    SimulationResult,
    VolumeTotal,
)
from app.domain.enums import MatchStatus
from app.domain.errors import ValidationFailedError
from app.domain.facts import Fact, calculated, unavailable
from app.domain.ids import new_id
from app.domain.models import Assumptions, AuditEvent, utcnow
from app.impact.engine import LineOverride
from app.impact.models import ImpactResult
from app.ingestion.service import ensure_not_busy
from app.risk.engine import UNRESOLVED, sort_risks

router = APIRouter(prefix="/projects/{pid}", tags=["insights"])

MAX_NEXT_ACTIONS = 6


@router.get("/overview", response_model=Overview)
async def overview(pid: str, container: ContainerDep) -> Overview:
    insights = container.insights
    data = await insights.load(pid)
    project = data.project
    results = {v: insights.impact(data, v) for v in project.build_quantities}
    primary = results[project.build_quantities[0]]
    risks = await insights.risks(pid)
    summary = insights.summary(data, risks, primary)

    actions: list[NextAction] = [
        NextAction(label=f"{r.title}: {line_label}", risk_id=r.id, line_id=r.line_id)
        for r in sort_risks([r for r in risks if r.status in UNRESOLVED])
        for line_label in [
            next(
                (
                    line.mpn or line.description or line.id
                    for line in data.lines
                    if line.id == r.line_id
                ),
                "",
            )
        ]
    ][:MAX_NEXT_ACTIONS]
    if not risks and data.lines:
        actions.append(NextAction(label="No open risks: create a quote version"))

    return Overview(
        project_id=pid,
        status=project.status,
        data_mode=project.data_mode,
        currency=project.currency,
        lines=len(data.lines),
        matched=sum(1 for line in data.lines if line.match.status is MatchStatus.MATCHED),
        unpriced_lines=len(primary.unpriced_line_ids),
        totals_by_volume=[
            VolumeTotal(
                volume=v,
                material=r.totals.material,
                total=r.totals.grand_total,
                per_unit=r.totals.per_unit,
            )
            for v, r in results.items()
        ],
        risks=summary,
        next_actions=actions,
    )


@router.get("/assumptions", response_model=Assumptions)
async def get_assumptions(pid: str, container: ContainerDep) -> Assumptions:
    return (await container.repos.projects.get(pid)).assumptions


@router.put("/assumptions", response_model=Assumptions)
async def put_assumptions(
    pid: str, body: Assumptions, container: ContainerDep, role: DemoRoleDep
) -> Assumptions:
    repos = container.repos
    project = await repos.projects.get(pid)
    ensure_not_busy(project)
    before = project.assumptions.model_dump(mode="json")
    project.assumptions = body
    project.updated_at = utcnow()
    await repos.projects.put(project)
    await repos.audit(pid).put(
        AuditEvent(
            id=new_id("aud"),
            actor_role=role,
            action="ASSUMPTIONS_UPDATED",
            target=f"project:{pid}",
            before=before,
            after=body.model_dump(mode="json"),
        )
    )
    if project.stats.lines:
        await container.insights.refresh(pid)
    return body


@router.get("/impact", response_model=ImpactResult)
async def impact(
    pid: str, container: ContainerDep, volume: Annotated[int | None, Query(ge=1)] = None
) -> ImpactResult:
    data = await container.insights.load(pid)
    return container.insights.impact(data, volume or data.project.build_quantities[0])


@router.post("/impact/simulate", response_model=SimulationResult)
async def simulate(pid: str, body: SimulationRequest, container: ContainerDep) -> SimulationResult:
    """What-if: never persisted, never changes the project."""
    insights = container.insights
    data = await insights.load(pid)
    known = {line.id for line in data.lines}
    unknown = [o.line_id for o in body.overrides if o.line_id not in known]
    if unknown:
        raise ValidationFailedError("Unknown line ids in overrides", {"line_ids": list(unknown)})
    overrides = {
        o.line_id: LineOverride(
            scrap_pct=o.scrap_pct, offer_id=o.offer_id, qty_per=o.qty_per, on_hand=o.on_hand
        )
        for o in body.overrides
    }
    baseline = insights.impact(data, body.volume)
    simulated = insights.impact(data, body.volume, overrides)
    before, after = baseline.totals.grand_total.value, simulated.totals.grand_total.value
    delta: Fact[Decimal] = (
        calculated(after - before, "simulated total − baseline total", unit=data.project.currency)
        if before is not None and after is not None
        else unavailable("A total is unavailable, so the difference cannot be computed")
    )
    return SimulationResult(baseline=baseline, simulated=simulated, delta=delta)
