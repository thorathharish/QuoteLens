"""Composition root: builds the process-wide dependencies from settings."""

from dataclasses import dataclass
from typing import Protocol

from app.config import JobBackend, Settings, StorageBackend
from app.infra.jobbus import InlineJobBus, PubSubJobBus
from app.infra.repositories import DocumentStore, Repositories
from app.infra.repositories.memory import InMemoryDocumentStore
from app.jobs.dispatcher import JobDispatcher


class JobBus(Protocol):
    async def publish(self, job_id: str) -> None: ...

    async def drain(self) -> None: ...


@dataclass
class Container:
    settings: Settings
    repos: Repositories
    dispatcher: JobDispatcher
    job_bus: JobBus


def build_store(settings: Settings) -> DocumentStore:
    if settings.storage_backend is StorageBackend.FIRESTORE:
        from app.infra.repositories.firestore import FirestoreDocumentStore

        return FirestoreDocumentStore.from_project(settings.gcp_project)
    return InMemoryDocumentStore()


def build_container(settings: Settings, store: DocumentStore | None = None) -> Container:
    repos = Repositories(store or build_store(settings))
    dispatcher = JobDispatcher(repos)
    # Job handlers are registered here as phases land (analysis: Phase 3, alternatives: Phase 5).

    job_bus: JobBus
    if settings.job_backend is JobBackend.PUBSUB:
        if not settings.gcp_project:
            raise ValueError("GCP_PROJECT is required when JOB_BACKEND=pubsub")
        job_bus = PubSubJobBus(settings.gcp_project, settings.pubsub_topic)
    else:
        job_bus = InlineJobBus(dispatcher.dispatch)
    return Container(settings=settings, repos=repos, dispatcher=dispatcher, job_bus=job_bus)
