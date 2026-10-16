"""Alternative parts: investigate (job), list, and decide (human gate 3)."""

from typing import Annotated

from fastapi import APIRouter, Header

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import (
    AlternativeDecision,
    AlternativeList,
    AlternativeSearch,
    DecisionResult,
    JobAccepted,
)
from app.domain.enums import AlternativeStatus, JobType
from app.infra.repositories import Filter
from app.jobs.dispatcher import enqueue_job

router = APIRouter(prefix="/projects/{pid}", tags=["alternatives"])


@router.post("/lines/{lid}/alternatives/search", status_code=202, response_model=JobAccepted)
async def search_alternatives(
    pid: str,
    lid: str,
    container: ContainerDep,
    body: AlternativeSearch | None = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> JobAccepted:
    repos = container.repos
    await repos.lines(pid).get(lid)  # 404 for unknown lines
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
    job = await enqueue_job(
        repos,
        container.job_bus,
        pid,
        JobType.ALTERNATIVES,
        payload={"line_id": lid, "reason": body.reason if body else None},
        idempotency_key=idempotency_key,
    )
    return JobAccepted(job_id=job.id)


@router.get("/alternatives", response_model=AlternativeList)
async def list_alternatives(
    pid: str,
    container: ContainerDep,
    line_id: str | None = None,
    status: AlternativeStatus | None = None,
) -> AlternativeList:
    await container.repos.projects.get(pid)
    items = await container.repos.alternatives(pid).all()
    filtered = [
        a
        for a in items
        if (line_id is None or a.line_id == line_id) and (status is None or a.status is status)
    ]
    return AlternativeList(items=sorted(filtered, key=lambda a: (a.line_id, a.fit_class.value)))


@router.post("/alternatives/{aid}/decision", response_model=DecisionResult)
async def decide(
    pid: str, aid: str, body: AlternativeDecision, container: ContainerDep, role: DemoRoleDep
) -> DecisionResult:
    alternative, line = await container.alternatives.decide(
        pid, aid, body.decision == "APPROVE", body.note, role
    )
    return DecisionResult(alternative=alternative, line=line)
