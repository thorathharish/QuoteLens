"""Composition root: builds the process-wide dependencies from settings."""

from dataclasses import dataclass
from typing import Protocol

from app.config import BlobBackend, JobBackend, Settings, StorageBackend
from app.domain.enums import JobType
from app.infra.blobstore import BlobStore, GcsBlobStore, InMemoryBlobStore
from app.infra.jobbus import InlineJobBus, PubSubJobBus
from app.infra.llm import ModelTier, build_chat_model
from app.infra.repositories import DocumentStore, Repositories
from app.infra.repositories.memory import InMemoryDocumentStore
from app.ingestion.column_mapper import GeminiHeaderMapper, HeaderMapper
from app.ingestion.service import IngestionService
from app.jobs.analysis import AnalysisPipeline
from app.jobs.dispatcher import JobDispatcher


class JobBus(Protocol):
    async def publish(self, job_id: str) -> None: ...

    async def drain(self) -> None: ...


@dataclass
class Container:
    settings: Settings
    repos: Repositories
    blobs: BlobStore
    dispatcher: JobDispatcher
    job_bus: JobBus
    ingestion: IngestionService


def build_store(settings: Settings) -> DocumentStore:
    if settings.storage_backend is StorageBackend.FIRESTORE:
        from app.infra.repositories.firestore import FirestoreDocumentStore

        return FirestoreDocumentStore.from_project(settings.gcp_project)
    return InMemoryDocumentStore()


def build_blobs(settings: Settings) -> BlobStore:
    if settings.blob_backend is BlobBackend.GCS:
        if not settings.gcs_bucket:
            raise ValueError("GCS_BUCKET is required when BLOB_BACKEND=gcs")
        return GcsBlobStore(settings.gcp_project, settings.gcs_bucket)
    return InMemoryBlobStore()


def build_header_mapper(settings: Settings) -> HeaderMapper | None:
    model = build_chat_model(settings, ModelTier.FLASH, max_output_tokens=512)
    return GeminiHeaderMapper(model) if model is not None else None


def build_container(
    settings: Settings,
    store: DocumentStore | None = None,
    blobs: BlobStore | None = None,
    header_mapper: HeaderMapper | None = None,
) -> Container:
    repos = Repositories(store or build_store(settings))
    blob_store = blobs or build_blobs(settings)
    dispatcher = JobDispatcher(repos)

    job_bus: JobBus
    if settings.job_backend is JobBackend.PUBSUB:
        if not settings.gcp_project:
            raise ValueError("GCP_PROJECT is required when JOB_BACKEND=pubsub")
        job_bus = PubSubJobBus(settings.gcp_project, settings.pubsub_topic)
    else:
        job_bus = InlineJobBus(dispatcher.dispatch)

    ingestion = IngestionService(
        repos=repos,
        blobs=blob_store,
        jobs=job_bus,
        settings=settings,
        header_mapper=header_mapper or build_header_mapper(settings),
    )
    dispatcher.register(JobType.ANALYSIS, AnalysisPipeline(repos=repos, ingestion=ingestion))
    return Container(
        settings=settings,
        repos=repos,
        blobs=blob_store,
        dispatcher=dispatcher,
        job_bus=job_bus,
        ingestion=ingestion,
    )
