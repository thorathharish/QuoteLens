"""Explainable risks: list with summary, detail with evidence, review (human gate 2)."""

from fastapi import APIRouter

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import RiskDetail, RiskList, RiskReview
from app.domain.enums import RiskCategory, RiskStatus, Severity
from app.domain.errors import ValidationFailedError
from app.domain.facts import Evidence
from app.domain.ids import new_id
from app.domain.models import AuditEvent, Risk
from app.ingestion.service import ensure_not_busy
from app.risk.engine import sort_risks

router = APIRouter(prefix="/projects/{pid}/risks", tags=["risks"])


@router.get("", response_model=RiskList)
async def list_risks(
    pid: str,
    container: ContainerDep,
    status: RiskStatus | None = None,
    severity: Severity | None = None,
    category: RiskCategory | None = None,
    line_id: str | None = None,
) -> RiskList:
    insights = container.insights
    data = await insights.load(pid)
    risks = await insights.risks(pid)
    summary = insights.summary(data, risks, insights.impact(data, data.project.build_quantities[0]))
    items = [
        r
        for r in risks
        if (status is None or r.status is status)
        and (severity is None or r.severity is severity)
        and (category is None or r.category is category)
        and (line_id is None or r.line_id == line_id)
    ]
    return RiskList(summary=summary, items=sort_risks(items))


@router.get("/{rid}", response_model=RiskDetail)
async def get_risk(pid: str, rid: str, container: ContainerDep) -> RiskDetail:
    risk = await container.repos.risks(pid).get(rid)
    return RiskDetail(risk=risk, evidence=await _evidence(container, pid, risk))


@router.patch("/{rid}", response_model=Risk)
async def review_risk(
    pid: str, rid: str, body: RiskReview, container: ContainerDep, role: DemoRoleDep
) -> Risk:
    if body.status is RiskStatus.WAIVED and not (body.note and body.note.strip()):
        raise ValidationFailedError("A note is required to waive a risk", {"field": "note"})
    repos = container.repos
    ensure_not_busy(await repos.projects.get(pid))
    risk = await repos.risks(pid).get(rid)
    updated = risk.model_copy(update={"status": body.status, "resolution_note": body.note})
    await repos.risks(pid).put(updated)
    await repos.audit(pid).put(
        AuditEvent(
            id=new_id("aud"),
            actor_role=role,
            action=f"RISK_{body.status.value}",
            target=f"risk:{rid}",
            before={"status": risk.status.value},
            after={"status": body.status.value},
            reason=body.note,
        )
    )
    await container.insights.refresh(pid)  # readiness and project status follow the decision
    return await repos.risks(pid).get(rid)


async def _evidence(container: ContainerDep, pid: str, risk: Risk) -> dict[str, Evidence]:
    found: dict[str, Evidence] = {}
    for ev_id in risk.evidence_ids:
        evidence = await container.repos.evidence(pid).find(ev_id)
        if evidence is not None:
            found[ev_id] = evidence
    return found
