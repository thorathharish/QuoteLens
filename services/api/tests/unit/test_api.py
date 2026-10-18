import base64

from httpx import AsyncClient

from app.config import Settings
from app.container import Container
from app.domain.enums import JobStatus, JobType
from app.domain.models import Job
from app.infra.jobbus import encode_job_message
from app.jobs.dispatcher import JobContext


async def test_healthz(api_client: AsyncClient) -> None:
    response = await api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reports_store(api_client: AsyncClient) -> None:
    response = await api_client.get("/readyz")
    assert response.json() == {"status": "ok", "deps": {"store": "ok"}}


async def test_request_id_is_generated_and_echoed(api_client: AsyncClient) -> None:
    generated = await api_client.get("/healthz")
    assert generated.headers["x-request-id"]

    echoed = await api_client.get("/healthz", headers={"X-Request-Id": "abc-123"})
    assert echoed.headers["x-request-id"] == "abc-123"

    unsafe = await api_client.get("/healthz", headers={"X-Request-Id": "bad id\nwith newline"})
    assert unsafe.headers["x-request-id"] != "bad id\nwith newline"


async def test_unknown_route_uses_error_envelope(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/does-not-exist", headers={"X-Request-Id": "req-1"})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == "req-1"


async def test_cors_allows_configured_origin(api_client: AsyncClient) -> None:
    response = await api_client.options(
        "/healthz",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def _push_body(data: bytes) -> dict[str, object]:
    return {
        "message": {"data": base64.b64encode(data).decode(), "messageId": "m1"},
        "subscription": "projects/p/subscriptions/s",
    }


async def test_worker_runs_pushed_job(worker_client: AsyncClient, container: Container) -> None:
    async def handler(job: Job, ctx: JobContext) -> None:
        return None

    container.dispatcher.register(JobType.ANALYSIS, handler, replace=True)
    await container.repos.jobs.put(Job(id="job_1", project_id="prj_1", type=JobType.ANALYSIS))

    response = await worker_client.post(
        "/internal/jobs/pubsub", json=_push_body(encode_job_message("job_1"))
    )

    assert response.status_code == 204
    assert (await container.repos.jobs.get("job_1")).status is JobStatus.SUCCEEDED


async def test_worker_rejects_malformed_message(worker_client: AsyncClient) -> None:
    response = await worker_client.post("/internal/jobs/pubsub", json=_push_body(b"not json"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_worker_requires_token_when_oidc_enabled() -> None:
    from httpx import ASGITransport

    from app.container import build_container
    from app.infra.repositories.memory import InMemoryDocumentStore
    from app.main_worker import create_app

    secure = Settings(
        env="test",
        pubsub_verify_oidc=True,
        pubsub_push_audience="https://worker.example",
        pubsub_push_service_account="push@example.iam.gserviceaccount.com",
        _env_file=None,  # type: ignore[call-arg]
    )
    app = create_app(build_container(secure, store=InMemoryDocumentStore()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/internal/jobs/pubsub", json=_push_body(encode_job_message("job_1"))
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_project_create_rejects_blank_names_and_duplicate_volumes(
    api_client: AsyncClient,
) -> None:
    for body in (
        {"name": "   ", "build_quantities": [100]},
        {"name": "Board", "build_quantities": [100, 100]},
    ):
        response = await api_client.post("/api/v1/projects", json=body)
        assert response.status_code == 422, body
    ok = await api_client.post(
        "/api/v1/projects", json={"name": "  Board  ", "customer": "  ", "build_quantities": [100]}
    )
    assert ok.status_code == 201
    assert ok.json()["name"] == "Board"
    assert ok.json()["customer"] is None
