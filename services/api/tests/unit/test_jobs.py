from app.container import Container
from app.domain.enums import JobStatus, JobType
from app.domain.errors import ValidationFailedError
from app.domain.models import Job
from app.infra.jobbus import InlineJobBus, decode_job_message, encode_job_message
from app.jobs.dispatcher import JobContext, enqueue_job


async def _enqueue_and_drain(container: Container, job_type: JobType = JobType.ANALYSIS) -> Job:
    job = await enqueue_job(container.repos, container.job_bus, "prj_1", job_type)
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()
    return await container.repos.jobs.get(job.id)


async def test_successful_job_records_progress_and_completion(container: Container) -> None:
    stages: list[str] = []

    async def handler(job: Job, ctx: JobContext) -> None:
        await ctx.progress("sourcing", 40)
        stages.append(ctx.job.stage or "")

    container.dispatcher.register(JobType.ANALYSIS, handler)
    job = await _enqueue_and_drain(container)

    assert stages == ["sourcing"]
    assert job.status is JobStatus.SUCCEEDED
    assert job.progress == 100
    assert job.started_at is not None
    assert job.finished_at is not None


async def test_domain_error_marks_job_failed_with_code(container: Container) -> None:
    async def handler(job: Job, ctx: JobContext) -> None:
        raise ValidationFailedError("BOM has no quantity column")

    container.dispatcher.register(JobType.ANALYSIS, handler)
    job = await _enqueue_and_drain(container)

    assert job.status is JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "VALIDATION_ERROR"


async def test_unexpected_error_is_not_leaked(container: Container) -> None:
    async def handler(job: Job, ctx: JobContext) -> None:
        raise RuntimeError("secret internal detail")

    container.dispatcher.register(JobType.ANALYSIS, handler)
    job = await _enqueue_and_drain(container)

    assert job.error is not None
    assert job.error.code == "INTERNAL"
    assert "secret" not in job.error.message


async def test_missing_handler_fails_job(container: Container) -> None:
    job = await _enqueue_and_drain(container, JobType.ALTERNATIVES)
    assert job.status is JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "NO_HANDLER"


async def test_redelivery_of_finished_job_is_a_no_op(container: Container) -> None:
    calls = 0

    async def handler(job: Job, ctx: JobContext) -> None:
        nonlocal calls
        calls += 1

    container.dispatcher.register(JobType.ANALYSIS, handler)
    job = await _enqueue_and_drain(container)
    await container.dispatcher.dispatch(job.id)

    assert calls == 1


def test_job_message_codec_round_trip() -> None:
    assert decode_job_message(encode_job_message("job_123")) == "job_123"
