"""Ad-hoc component lookup and analysis re-runs."""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import AnalysisRequest, ComponentLookup, JobAccepted
from app.domain.enums import DataMode, JobType, ProjectStatus
from app.domain.errors import ValidationFailedError
from app.domain.ids import new_id
from app.domain.models import AuditEvent, utcnow
from app.domain.mpn import normalize_mpn
from app.infra.repositories import Filter
from app.ingestion.service import ensure_not_busy
from app.jobs.dispatcher import enqueue_job

router = APIRouter(tags=["sourcing"])


@router.get("/components/lookup", response_model=ComponentLookup)
async def lookup_component(
    container: ContainerDep,
    mpn: Annotated[str, Query(min_length=1, max_length=64)],
    mode: DataMode = DataMode.CACHE_FIRST,
) -> ComponentLookup:
    key = normalize_mpn(mpn)
    if key is None:
        raise ValidationFailedError("MPN must not be empty")
    chain = container.sourcing.chain
    result = await chain.fetch([key], mode)
    component = result.components.get(key)
    return ComponentLookup(
        mpn=key,
        component=component,
        offers=result.offers.get(key, []),
        suggestions=[] if component else await chain.search.suggest(key),
        warnings=result.errors,
    )


@router.post("/projects/{pid}/analysis", status_code=202, response_model=JobAccepted)
async def rerun_analysis(
    pid: str,
    container: ContainerDep,
    role: DemoRoleDep,
    body: AnalysisRequest | None = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> JobAccepted:
    repos = container.repos
    if idempotency_key:
        existing = await repos.jobs.list(
            filters=[
                Filter("project_id", "==", pid),
                Filter("idempotency_key", "==", idempotency_key),
            ],
            limit=1,
        )
        if existing.items:
            return JobAccepted(job_id=existing.items[0].id)
    project = await repos.projects.get(pid)
    ensure_not_busy(project)
    if project.stats.lines == 0:
        raise ValidationFailedError("Upload and confirm a BOM before running analysis")

    line_ids = body.line_ids if body and body.line_ids else None
    project.status = ProjectStatus.ANALYZING
    project.updated_at = utcnow()
    await repos.projects.put(project)
    await repos.audit(pid).put(
        AuditEvent(
            id=new_id("aud"),
            actor_role=role,
            action="ANALYSIS_REQUESTED",
            target=f"project:{pid}",
            after={"line_ids": list(line_ids) if line_ids else None},
        )
    )
    job = await enqueue_job(
        repos,
        container.job_bus,
        pid,
        JobType.ANALYSIS,
        payload={"line_ids": list(line_ids)} if line_ids else {},
        idempotency_key=idempotency_key,
    )
    return JobAccepted(job_id=job.id)
