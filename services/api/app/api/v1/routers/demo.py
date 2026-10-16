"""Guided demo: seed a sample project in one click."""

from fastapi import APIRouter

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import DemoSeed, DemoSeeded

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/projects", status_code=201, response_model=DemoSeeded)
async def seed_demo(body: DemoSeed, container: ContainerDep, role: DemoRoleDep) -> DemoSeeded:
    project, job = await container.demo.seed(body.scenario, role)
    return DemoSeeded(project_id=project.id, job_id=job.id)
