"""FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Header, Request

from app.container import Container
from app.domain.enums import DemoRole
from app.infra.repositories import Repositories


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_repos(container: Annotated[Container, Depends(get_container)]) -> Repositories:
    return container.repos


def get_demo_role(
    x_demo_role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = DemoRole.VIEWER,
) -> DemoRole:
    """Role from the UI role switcher. Audit attribution only; it grants nothing."""
    return x_demo_role


ContainerDep = Annotated[Container, Depends(get_container)]
ReposDep = Annotated[Repositories, Depends(get_repos)]
DemoRoleDep = Annotated[DemoRole, Depends(get_demo_role)]
