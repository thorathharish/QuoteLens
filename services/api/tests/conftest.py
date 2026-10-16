from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import JobBackend, Settings, StorageBackend
from app.container import Container, build_container
from app.infra.repositories import Repositories
from app.infra.repositories.memory import InMemoryDocumentStore


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        storage_backend=StorageBackend.MEMORY,
        job_backend=JobBackend.INLINE,
        llm_enabled=False,
        pubsub_verify_oidc=False,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings, store=InMemoryDocumentStore())


@pytest.fixture
def repos(container: Container) -> Repositories:
    return container.repos


@pytest.fixture
async def api_client(container: Container) -> AsyncIterator[AsyncClient]:
    from app.main_api import create_app

    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def worker_client(container: Container) -> AsyncIterator[AsyncClient]:
    from app.main_worker import create_app

    app = create_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
