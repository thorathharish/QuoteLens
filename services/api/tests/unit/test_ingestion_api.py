"""End-to-end through the HTTP API with in-memory storage and inline jobs."""

from pathlib import Path
from typing import Any

from httpx import AsyncClient

from app.container import Container
from app.domain.enums import ProjectStatus
from app.infra.jobbus import InlineJobBus

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _create_project(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/projects",
        json={"name": "MC48 controller", "customer": "ACME", "build_quantities": [100, 1000, 5000]},
        headers={"X-Demo-Role": "QUOTE_ENGINEER"},
    )
    assert response.status_code == 201, response.text
    project_id: str = response.json()["id"]
    return project_id


async def _upload(
    client: AsyncClient, pid: str, name: str = "motor_controller.xlsx"
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{pid}/bom",
        files={"file": (name, (SAMPLES / name).read_bytes(), XLSX)},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _drain(container: Container) -> None:
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()


async def test_upload_confirm_and_list_lines(api_client: AsyncClient, container: Container) -> None:
    pid = await _create_project(api_client)
    preview = await _upload(api_client, pid)
    assert preview["header_row"] == 1
    assert preview["selected_sheet"] == "BOM"
    assert preview["sheets"] == ["BOM", "Notes"]
    assert preview["data_rows"] == 60
    assert len(preview["preview_rows"]) == 10
    mapped = {m["field"] for m in preview["proposed_mapping"] if m["field"]}
    assert {"mpn", "manufacturer", "qty_per", "refdes", "dnp", "unit_price", "cpn"} <= mapped
    assert (await api_client.get(f"/api/v1/projects/{pid}")).json()["status"] == "MAPPING_REVIEW"

    accepted = await api_client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={"upload_id": preview["upload_id"], "mapping": []},
        headers={"X-Demo-Role": "QUOTE_ENGINEER"},
    )
    assert accepted.status_code == 202, accepted.text
    await _drain(container)

    job = (await api_client.get(f"/api/v1/jobs/{accepted.json()['job_id']}")).json()
    assert job["status"] == "SUCCEEDED", job
    project = (await api_client.get(f"/api/v1/projects/{pid}")).json()
    assert project["status"] == "IN_REVIEW"
    assert project["stats"]["lines"] == 59
    assert project["source_file"]["filename"] == "motor_controller.xlsx"

    lines = (await api_client.get(f"/api/v1/projects/{pid}/lines", params={"limit": 500})).json()
    assert len(lines["items"]) == 59
    assert lines["issue_counts"]["MISSING_MPN"] == 1
    blockers = (
        await api_client.get(f"/api/v1/projects/{pid}/lines", params={"issue": "QTY_INVALID"})
    ).json()
    assert [line["mpn"] for line in blockers["items"]] == ["0430450200"]

    audit = await container.repos.audit(pid).all()
    assert {e.action for e in audit} == {"PROJECT_CREATED", "MAPPING_CONFIRMED"}


async def test_user_override_is_recorded_and_required_fields_enforced(
    api_client: AsyncClient,
) -> None:
    pid = await _create_project(api_client)
    preview = await _upload(api_client, pid)
    qty_column = next(
        m["column_index"] for m in preview["proposed_mapping"] if m["field"] == "qty_per"
    )

    missing = await api_client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={
            "upload_id": preview["upload_id"],
            "mapping": [{"column_index": qty_column, "field": None}],
        },
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["details"]["missing"] == ["qty_per"]

    duplicate = await api_client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={
            "upload_id": preview["upload_id"],
            "mapping": [{"column_index": 0, "field": "mpn"}, {"column_index": 1, "field": "mpn"}],
        },
    )
    assert duplicate.status_code == 422


async def test_idempotency_key_and_busy_project(
    api_client: AsyncClient, container: Container
) -> None:
    pid = await _create_project(api_client)
    preview = await _upload(api_client, pid)
    body = {"upload_id": preview["upload_id"], "mapping": []}
    headers = {"Idempotency-Key": "confirm-1"}

    first = await api_client.put(f"/api/v1/projects/{pid}/bom/mapping", json=body, headers=headers)
    again = await api_client.put(f"/api/v1/projects/{pid}/bom/mapping", json=body, headers=headers)
    assert first.json()["job_id"] == again.json()["job_id"]

    await _drain(container)

    project = await container.repos.projects.get(pid)
    project.status = ProjectStatus.ANALYZING  # as if a job were still running
    await container.repos.projects.put(project)
    busy = await api_client.put(f"/api/v1/projects/{pid}/bom/mapping", json=body)
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "INVALID_STATE"


async def test_messy_file_detects_header_below_title_block(api_client: AsyncClient) -> None:
    pid = await _create_project(api_client)
    preview = await _upload(api_client, pid, "messy_format.xlsx")
    assert preview["header_row"] == 5
    assert "Sl No" in preview["unmapped"]


async def test_upload_errors_use_the_envelope(api_client: AsyncClient) -> None:
    pid = await _create_project(api_client)
    bad = await api_client.post(
        f"/api/v1/projects/{pid}/bom", files={"file": ("bom.pdf", b"%PDF-1.7", "application/pdf")}
    )
    assert bad.status_code == 415
    assert bad.json()["error"]["code"] == "UNSUPPORTED_FILE"

    encrypted = await api_client.post(
        f"/api/v1/projects/{pid}/bom",
        files={"file": ("bom.xlsx", bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 512)},
    )
    assert encrypted.status_code == 415
    assert "password-protected" in encrypted.json()["error"]["message"]

    no_header = await api_client.post(
        f"/api/v1/projects/{pid}/bom", files={"file": ("bom.csv", b"a,b\n1,2\n", "text/csv")}
    )
    assert no_header.status_code == 422

    header_only = await api_client.post(
        f"/api/v1/projects/{pid}/bom",
        files={"file": ("bom.csv", b"Reference,Quantity,Manufacturer,MPN\n", "text/csv")},
    )
    assert header_only.status_code == 422
    assert "no BOM lines" in header_only.json()["error"]["message"]

    missing = await api_client.post(
        "/api/v1/projects/prj_missing/bom",
        files={"file": ("bom.csv", b"MPN,Qty\nX,1\n", "text/csv")},
    )
    assert missing.status_code == 404


async def test_project_validation_list_and_delete(
    api_client: AsyncClient, container: Container
) -> None:
    invalid = await api_client.post("/api/v1/projects", json={"name": "x", "build_quantities": [0]})
    assert invalid.status_code == 422

    pid = await _create_project(api_client)
    await _upload(api_client, pid)
    listed = (await api_client.get("/api/v1/projects")).json()
    assert pid in [p["id"] for p in listed["items"]]

    refused = await api_client.delete(
        f"/api/v1/projects/{pid}", headers={"X-Demo-Role": "QUOTE_ENGINEER"}
    )
    assert refused.status_code == 403
    deleted = await api_client.delete(f"/api/v1/projects/{pid}", headers={"X-Demo-Role": "MANAGER"})
    assert deleted.status_code == 204
    assert (await api_client.get(f"/api/v1/projects/{pid}")).status_code == 404
    assert await container.repos.uploads(pid).all() == []
