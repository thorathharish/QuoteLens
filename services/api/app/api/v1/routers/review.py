"""Line corrections, audit trail and evidence lookup."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.routers.lines import line_detail
from app.api.v1.schemas import AuditList, LineDetail, LinePatch
from app.domain.facts import Evidence
from app.infra.repositories import OrderBy
from app.sourcing.review import LineChanges

router = APIRouter(prefix="/projects/{pid}", tags=["review"])


@router.patch("/lines/{lid}", response_model=LineDetail)
async def edit_line(
    pid: str, lid: str, body: LinePatch, container: ContainerDep, role: DemoRoleDep
) -> LineDetail:
    changes = LineChanges(**body.changes.model_dump(exclude_unset=True))
    line = await container.review.edit_line(pid, lid, changes, body.reason, role)
    return await line_detail(container.repos, pid, line)


@router.get("/audit", response_model=AuditList)
async def audit(
    pid: str, container: ContainerDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200
) -> AuditList:
    await container.repos.projects.get(pid)
    events = await container.repos.audit(pid).all(order_by=OrderBy("at", descending=True))
    return AuditList(items=events[:limit])


@router.get("/evidence/{eid}", response_model=Evidence)
async def evidence(pid: str, eid: str, container: ContainerDep) -> Evidence:
    return await container.repos.evidence(pid).get(eid)
