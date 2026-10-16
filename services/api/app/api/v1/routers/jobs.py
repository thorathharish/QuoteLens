"""Background job status (polled by the UI while analysis runs)."""

from fastapi import APIRouter

from app.api.deps import ReposDep
from app.domain.models import Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=Job, response_model_exclude={"idempotency_key"})
async def get_job(job_id: str, repos: ReposDep) -> Job:
    return await repos.jobs.get(job_id)
