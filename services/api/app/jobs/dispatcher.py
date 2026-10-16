"""Background job lifecycle: enqueue, dispatch to a handler, record progress and outcome.

Delivery is at-least-once (Pub/Sub), so dispatch is idempotent: a job that already
finished is not run again. Handlers themselves must be safe to re-run after a crash.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import JsonValue

from app.domain.enums import JobStatus, JobType
from app.domain.errors import DomainError
from app.domain.ids import new_id
from app.domain.models import Job, JobError, utcnow
from app.infra.repositories import Repositories
from app.logging import job_id_var, project_id_var

logger = logging.getLogger(__name__)


class JobPublisher(Protocol):
    async def publish(self, job_id: str) -> None: ...


class JobContext:
    """Handed to handlers so they can report progress without touching storage directly."""

    def __init__(self, job: Job, repos: Repositories) -> None:
        self.job = job
        self._repos = repos

    async def progress(self, stage: str, percent: int) -> None:
        self.job.stage = stage
        self.job.progress = max(self.job.progress, min(percent, 99))
        await self._repos.jobs.put(self.job)

    async def warn(self, message: str) -> None:
        self.job.warnings = [*self.job.warnings, message]
        await self._repos.jobs.put(self.job)


JobHandler = Callable[[Job, JobContext], Awaitable[None]]


class JobDispatcher:
    def __init__(self, repos: Repositories) -> None:
        self._repos = repos
        self._handlers: dict[JobType, JobHandler] = {}

    def register(self, job_type: JobType, handler: JobHandler) -> None:
        if job_type in self._handlers:
            raise ValueError(f"Handler for {job_type} already registered")
        self._handlers[job_type] = handler

    async def dispatch(self, job_id: str) -> Job | None:
        job = await self._repos.jobs.find(job_id)
        if job is None:
            logger.warning("Job not found; dropping message", extra={"fields": {"job": job_id}})
            return None
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            logger.info("Job already finished; skipping redelivery")
            return job

        job_token = job_id_var.set(job.id)
        project_token = project_id_var.set(job.project_id)
        try:
            return await self._run(job)
        finally:
            job_id_var.reset(job_token)
            project_id_var.reset(project_token)

    async def _run(self, job: Job) -> Job:
        handler = self._handlers.get(job.type)
        if handler is None:
            return await self._finish(
                job, JobError(code="NO_HANDLER", message=f"No handler for {job.type}")
            )

        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        await self._repos.jobs.put(job)
        logger.info("Job started", extra={"fields": {"type": job.type}})
        try:
            await handler(job, JobContext(job, self._repos))
        except DomainError as exc:
            logger.warning("Job failed: %s", exc.message)
            return await self._finish(job, JobError(code=exc.code, message=exc.message))
        except Exception:
            logger.exception("Job crashed")
            return await self._finish(
                job, JobError(code="INTERNAL", message="Unexpected error while processing job")
            )
        return await self._finish(job, None)

    async def _finish(self, job: Job, error: JobError | None) -> Job:
        job.status = JobStatus.FAILED if error else JobStatus.SUCCEEDED
        job.error = error
        if error is None:
            job.progress = 100
        job.finished_at = utcnow()
        await self._repos.jobs.put(job)
        logger.info("Job finished", extra={"fields": {"status": job.status}})
        return job


async def enqueue_job(
    repos: Repositories,
    publisher: JobPublisher,
    project_id: str,
    job_type: JobType,
    payload: dict[str, JsonValue] | None = None,
) -> Job:
    """Persist a QUEUED job, then publish its id. The message carries only the id."""
    job = Job(id=new_id("job"), project_id=project_id, type=job_type, payload=payload or {})
    await repos.jobs.put(job)
    await publisher.publish(job.id)
    return job
