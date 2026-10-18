"""Projects: create, list, get, delete."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import ContainerDep, DemoRoleDep, ReposDep
from app.api.v1.schemas import ProjectCreate, ProjectPage
from app.domain.enums import DemoRole
from app.domain.errors import ForbiddenError
from app.domain.ids import new_id
from app.domain.models import AuditEvent, Project
from app.infra.repositories import OrderBy

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", status_code=201, response_model=Project)
async def create_project(body: ProjectCreate, repos: ReposDep, role: DemoRoleDep) -> Project:
    project = Project(id=new_id("prj"), **body.model_dump())
    await repos.projects.put(project)
    await repos.audit(project.id).put(
        AuditEvent(
            id=new_id("aud"),
            actor_role=role,
            action="PROJECT_CREATED",
            target=f"project:{project.id}",
            after={"name": project.name},
        )
    )
    return project


@router.get("", response_model=ProjectPage)
async def list_projects(
    repos: ReposDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> ProjectPage:
    page = await repos.projects.list(
        order_by=OrderBy("created_at", descending=True), limit=limit, cursor=cursor
    )
    return ProjectPage(items=page.items, next_cursor=page.next_cursor)


@router.get("/{pid}", response_model=Project)
async def get_project(pid: str, repos: ReposDep) -> Project:
    return await repos.projects.get(pid)


@router.delete("/{pid}", status_code=204)
async def delete_project(pid: str, container: ContainerDep, role: DemoRoleDep) -> Response:
    # The demo has no login, so any visitor could delete anyone's project. Deleting is
    # limited to the program manager role (still a demo control, not security).
    if role is not DemoRole.MANAGER:
        raise ForbiddenError("Only a program manager can delete a project")
    await container.repos.projects.get(pid)  # 404 if missing
    await container.repos.projects.delete(pid)
    await container.blobs.delete_prefix(f"uploads/{pid}/")
    return Response(status_code=204)
