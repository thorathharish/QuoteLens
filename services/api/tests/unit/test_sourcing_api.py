"""Phase 3 end to end: the hero BOM through parse → sourcing via the HTTP API."""

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.container import Container
from app.infra.jobbus import InlineJobBus

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _drain(container: Container) -> None:
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()


@pytest.fixture
async def analyzed(
    api_client: AsyncClient, container: Container
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Project with motor_controller.xlsx analyzed; returns (pid, lines by MPN or refdes)."""
    created = await api_client.post(
        "/api/v1/projects", json={"name": "MC48", "build_quantities": [100, 1000, 5000]}
    )
    pid = created.json()["id"]
    upload = await api_client.post(
        f"/api/v1/projects/{pid}/bom",
        files={
            "file": (
                "motor_controller.xlsx",
                (SAMPLES / "motor_controller.xlsx").read_bytes(),
                XLSX,
            )
        },
    )
    job = await api_client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={"upload_id": upload.json()["upload_id"], "mapping": []},
    )
    await _drain(container)
    status = (await api_client.get(f"/api/v1/jobs/{job.json()['job_id']}")).json()
    assert status["status"] == "SUCCEEDED", status
    items = (await api_client.get(f"/api/v1/projects/{pid}/lines", params={"limit": 500})).json()[
        "items"
    ]
    by_key = {
        (line["mpn"] or line["refdes"][0]) + ("#dnp" if line["dnp"] else ""): line for line in items
    }
    return pid, by_key


async def test_hero_bom_sourcing_scenarios(
    api_client: AsyncClient, analyzed: tuple[str, dict[str, dict[str, Any]]]
) -> None:
    pid, lines = analyzed
    project = (await api_client.get(f"/api/v1/projects/{pid}")).json()
    # 59 lines - F1 (no MPN) - TPS5431DDR (typo) - R44 (DNP) = 56 matched
    assert project["stats"]["matched"] == 56
    assert project["status"] == "IN_REVIEW"

    typo = lines["TPS5431DDR"]
    assert typo["match"]["status"] == "NOT_FOUND"
    assert typo["match"]["candidates"] == ["TPS54331DDR"]
    assert typo["selected_offer_id"] is None

    obsolete = lines["A1101ELHLT-T"]["recommendation"]
    assert obsolete["offer_id"] is None
    assert any("not an authorized distributor" in r for r in obsolete["reasons"])
    assert any("obsolete" in r for r in obsolete["reasons"])

    single = await api_client.get(
        f"/api/v1/projects/{pid}/lines/{lines['STM32G431CBT6']['id']}/offers"
    )
    assert [o["distributor"] for o in single.json()["offers"]] == ["DigiKey"]

    outlier = await api_client.get(f"/api/v1/projects/{pid}/lines/{lines['INA240A1PWR']['id']}")
    detail = outlier.json()
    assert detail["selected_offer"]["distributor"] != "Mouser"  # Mouser is ~2.3x
    assert len(detail["offers"]) == 3

    long_lead = lines["DRV8323RSRGZR"]["recommendation"]
    assert any("Stock covers only" in r and "112 days" in r for r in long_lead["reasons"])

    reel = lines["SRP1265A-220M"]["recommendation"]
    assert any("extra units" in r for r in reel["reasons"])  # MOQ 500 vs 100 needed

    assert lines["RC0603FR-071KL#dnp"]["recommendation"] is None


async def test_line_detail_carries_evidence_for_every_source(
    api_client: AsyncClient, analyzed: tuple[str, dict[str, dict[str, Any]]]
) -> None:
    pid, lines = analyzed
    detail = (
        await api_client.get(f"/api/v1/projects/{pid}/lines/{lines['A1101ELHLT-T']['id']}")
    ).json()
    assert detail["component"]["lifecycle"] == "OBSOLETE"
    evidence = detail["evidence"]
    assert detail["component"]["evidence_id"] in evidence
    assert all(o["evidence_id"] in evidence for o in detail["offers"])
    assert any(e["kind"] == "BOM_CELL" for e in evidence.values())
    offer_ev = evidence[detail["offers"][0]["evidence_id"]]
    assert offer_ev["mode"] == "DEMO_SNAPSHOT"
    assert "demo snapshot" in offer_ev["source_name"]


async def test_fixing_mpns_resolves_typos_and_missing_parts(
    api_client: AsyncClient, analyzed: tuple[str, dict[str, dict[str, Any]]]
) -> None:
    pid, lines = analyzed
    typo_id = lines["TPS5431DDR"]["id"]
    fixed = await api_client.post(
        f"/api/v1/projects/{pid}/lines/{typo_id}/match",
        json={"mpn": "TPS54331DDR", "reason": "Accepted suggested match"},
        headers={"X-Demo-Role": "SOURCING"},
    )
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert body["line"]["match"]["status"] == "MATCHED"
    assert body["line"]["mpn_raw"] == "TPS5431DDR"  # the original stays visible
    assert body["line"]["overrides"]["mpn"]["by"] == "SOURCING"
    assert body["selected_offer"] is not None

    fuse_id = lines["F1"]["id"]
    fuse = await api_client.post(
        f"/api/v1/projects/{pid}/lines/{fuse_id}/match",
        json={
            "mpn": "0451005.MRL",
            "manufacturer": "Littelfuse",
            "reason": "Confirmed with customer",
        },
    )
    fuse_line = fuse.json()["line"]
    assert fuse_line["match"]["status"] == "MATCHED"
    assert "MISSING_MPN" not in {i["code"] for i in fuse_line["validation"]}
    assert fuse_line["version"] == 2


async def test_offer_override_is_audited_and_survives_rerun(
    api_client: AsyncClient, container: Container, analyzed: tuple[str, dict[str, dict[str, Any]]]
) -> None:
    pid, lines = analyzed
    line_id = lines["LM5164DDAR"]["id"]
    detail = (await api_client.get(f"/api/v1/projects/{pid}/lines/{line_id}")).json()
    alternative = next(
        o for o in detail["offers"] if o["id"] != detail["recommendation"]["offer_id"]
    )

    chosen = await api_client.put(
        f"/api/v1/projects/{pid}/lines/{line_id}/selected-offer",
        json={"offer_id": alternative["id"], "reason": "Preferred supplier agreement"},
        headers={"X-Demo-Role": "SOURCING"},
    )
    assert chosen.json()["selected_offer"]["id"] == alternative["id"]

    rerun = await api_client.post(f"/api/v1/projects/{pid}/analysis", json={})
    assert rerun.status_code == 202
    await _drain(container)
    after = (await api_client.get(f"/api/v1/projects/{pid}/lines/{line_id}")).json()
    assert after["line"]["selected_offer_id"] == alternative["id"]

    actions = [e.action for e in await container.repos.audit(pid).all()]
    assert "OFFER_SELECTED" in actions
    assert "ANALYSIS_REQUESTED" in actions

    foreign = await api_client.put(
        f"/api/v1/projects/{pid}/lines/{line_id}/selected-offer",
        json={"offer_id": "off_not_mine", "reason": "test"},
    )
    assert foreign.status_code == 422


async def test_component_lookup(api_client: AsyncClient) -> None:
    found = (
        await api_client.get("/api/v1/components/lookup", params={"mpn": "ina240a1pwr"})
    ).json()
    assert found["component"]["manufacturer"] == "Texas Instruments"
    assert len(found["offers"]) == 3
    missing = (
        await api_client.get("/api/v1/components/lookup", params={"mpn": "TPS5431DDR"})
    ).json()
    assert missing["component"] is None
    assert missing["suggestions"] == ["TPS54331DDR"]


async def test_rerun_requires_lines(api_client: AsyncClient) -> None:
    pid = (
        await api_client.post("/api/v1/projects", json={"name": "Empty", "build_quantities": [1]})
    ).json()["id"]
    response = await api_client.post(f"/api/v1/projects/{pid}/analysis")
    assert response.status_code == 422
