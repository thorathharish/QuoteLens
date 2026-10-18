"""Phase 4 end to end on the hero BOM: seeded risks, readiness gate, impact, what-if.

The golden snapshot (tests/golden/motor_controller.json) freezes per-volume totals and the
full risk list. Regenerate after an intended change with UPDATE_GOLDEN=1 and review the diff.
"""

import json
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.container import Container
from app.infra.jobbus import InlineJobBus

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"
GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "motor_controller.json"


@pytest.fixture
async def project(api_client: AsyncClient, container: Container) -> dict[str, Any]:
    target = (date.today() + timedelta(days=56)).isoformat()
    created = await api_client.post(
        "/api/v1/projects",
        json={"name": "MC48", "build_quantities": [100, 1000, 5000], "target_ship_date": target},
    )
    pid = created.json()["id"]
    upload = await api_client.post(
        f"/api/v1/projects/{pid}/bom",
        files={"file": ("motor_controller.xlsx", (SAMPLES / "motor_controller.xlsx").read_bytes())},
    )
    await api_client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={"upload_id": upload.json()["upload_id"], "mapping": []},
    )
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()
    lines = (await api_client.get(f"/api/v1/projects/{pid}/lines", params={"limit": 500})).json()[
        "items"
    ]
    return {"pid": pid, "lines": {line["id"]: line for line in lines}}


def _label(line: dict[str, Any]) -> str:
    return str(line["mpn"] or line["refdes"][0])


async def _risks(client: AsyncClient, pid: str) -> dict[str, Any]:
    body: dict[str, Any] = (await client.get(f"/api/v1/projects/{pid}/risks")).json()
    return body


async def test_seeded_risks_and_golden_snapshot(
    api_client: AsyncClient, project: dict[str, Any]
) -> None:
    pid, lines = project["pid"], project["lines"]
    risks = await _risks(api_client, pid)
    produced = {(r["rule_id"], r["line_id"]) for r in risks["items"]}

    manifest = json.loads((SAMPLES / "motor_controller.expected.json").read_text(encoding="utf-8"))
    for row in manifest["seeded_rows"]:
        spreadsheet_row = manifest["header_row"] + row["row"]
        line_id = next(x["id"] for x in lines.values() if spreadsheet_row in x["source_rows"])
        for rule in row["risks"]:
            assert (rule, line_id) in produced, f"{rule} missing on row {row['row']} ({row['mpn']})"

    assert risks["summary"]["open_blockers"] == manifest["open_blockers"] == 3
    for risk in risks["items"]:
        assert risk["why"]
        assert risk["evidence_ids"]
        assert risk["suggested_actions"]

    overview = (await api_client.get(f"/api/v1/projects/{pid}/overview")).json()
    snapshot = {
        "totals": {str(t["volume"]): t["total"]["value"] for t in overview["totals_by_volume"]},
        "unpriced_lines": overview["unpriced_lines"],
        "risks": sorted(
            f"{r['severity']} {r['rule_id']} {_label(lines[r['line_id']])}" for r in risks["items"]
        ),
    }
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    assert snapshot == json.loads(GOLDEN.read_text(encoding="utf-8"))


async def test_overview_shape_and_next_actions(
    api_client: AsyncClient, project: dict[str, Any]
) -> None:
    overview = (await api_client.get(f"/api/v1/projects/{project['pid']}/overview")).json()
    assert overview["status"] == "IN_REVIEW"
    assert overview["matched"] == 56
    assert [t["volume"] for t in overview["totals_by_volume"]] == [100, 1000, 5000]
    first = overview["totals_by_volume"][0]
    assert first["total"]["provenance"] == "CALCULATED"
    assert first["total"]["note"] == "Excludes 4 unpriced line(s)"
    assert overview["next_actions"][0]["label"].startswith(("Missing", "Invalid", "Part is"))
    assert overview["risks"]["spend_at_risk_pct"]["provenance"] == "CALCULATED"


async def test_review_gate_moves_project_to_quote_ready(
    api_client: AsyncClient, container: Container, project: dict[str, Any]
) -> None:
    pid, lines = project["pid"], project["lines"]
    blockers = [r for r in (await _risks(api_client, pid))["items"] if r["severity"] == "BLOCKER"]
    by_rule = {r["rule_id"]: r for r in blockers}

    no_note = await api_client.patch(
        f"/api/v1/projects/{pid}/risks/{by_rule['D04']['id']}", json={"status": "WAIVED"}
    )
    assert no_note.status_code == 422
    one_char = await api_client.patch(
        f"/api/v1/projects/{pid}/risks/{by_rule['D04']['id']}",
        json={"status": "WAIVED", "note": " x "},
    )
    assert one_char.status_code == 422

    fuse = next(x for x in lines.values() if x["refdes"] == ["F1"])
    fixed = await api_client.post(
        f"/api/v1/projects/{pid}/lines/{fuse['id']}/match",
        json={"mpn": "0451005.MRL", "reason": "Customer confirmed"},
    )
    assert fixed.status_code == 200
    for rule in ("D04", "L01"):
        waived = await api_client.patch(
            f"/api/v1/projects/{pid}/risks/{by_rule[rule]['id']}",
            json={"status": "WAIVED", "note": "Accepted for the demo quote"},
            headers={"X-Demo-Role": "MANAGER"},
        )
        assert waived.json()["status"] == "WAIVED"

    after = await _risks(api_client, pid)
    assert after["summary"]["open_blockers"] == 0
    assert after["summary"]["ready"] is True
    assert "D01" not in {r["rule_id"] for r in after["items"]}  # fixed data removes the risk
    assert (await api_client.get(f"/api/v1/projects/{pid}")).json()["status"] == "QUOTE_READY"

    # Decisions survive a full re-analysis
    await api_client.post(f"/api/v1/projects/{pid}/analysis")
    await container.job_bus.drain()  # type: ignore[attr-defined]
    rerun = {r["id"]: r for r in (await _risks(api_client, pid))["items"]}
    assert rerun[by_rule["L01"]["id"]]["status"] == "WAIVED"
    actions = {e.action for e in await container.repos.audit(pid).all()}
    assert {"RISK_WAIVED", "LINE_MPN_SET"} <= actions


async def test_risk_detail_includes_evidence(
    api_client: AsyncClient, project: dict[str, Any]
) -> None:
    pid = project["pid"]
    l01 = next(r for r in (await _risks(api_client, pid))["items"] if r["rule_id"] == "L01")
    detail = (await api_client.get(f"/api/v1/projects/{pid}/risks/{l01['id']}")).json()
    kinds = {e["kind"] for e in detail["evidence"].values()}
    assert {"CATALOG_SNAPSHOT", "DISTRIBUTOR_OFFER"} <= kinds
    filtered = (
        await api_client.get(f"/api/v1/projects/{pid}/risks", params={"severity": "BLOCKER"})
    ).json()["items"]
    assert len(filtered) == 3


async def test_impact_assumptions_and_simulation(
    api_client: AsyncClient, project: dict[str, Any]
) -> None:
    pid, lines = project["pid"], project["lines"]
    small = (await api_client.get(f"/api/v1/projects/{pid}/impact", params={"volume": 100})).json()
    assert small["recommendations"]  # price-break jumps exist at low volume
    assert all(r["saving"]["provenance"] == "RECOMMENDED" for r in small["recommendations"])

    impact = (
        await api_client.get(f"/api/v1/projects/{pid}/impact", params={"volume": 1000})
    ).json()
    assert impact["volume"] == 1000
    base_total = Decimal(impact["totals"]["grand_total"]["value"])

    srp = next(line["id"] for line in lines.values() if line["mpn"] == "SRP1265A-220M")
    sim = (
        await api_client.post(
            f"/api/v1/projects/{pid}/impact/simulate",
            json={"volume": 1000, "overrides": [{"line_id": srp, "scrap_pct": "0"}]},
        )
    ).json()
    assert Decimal(sim["baseline"]["totals"]["grand_total"]["value"]) == base_total
    assert Decimal(sim["delta"]["value"]) <= 0
    unchanged = (
        await api_client.get(f"/api/v1/projects/{pid}/impact", params={"volume": 1000})
    ).json()
    assert unchanged["totals"]["grand_total"]["value"] == impact["totals"]["grand_total"]["value"]

    bad = await api_client.post(
        f"/api/v1/projects/{pid}/impact/simulate",
        json={"volume": 10, "overrides": [{"line_id": "nope"}]},
    )
    assert bad.status_code == 422

    updated = await api_client.put(
        f"/api/v1/projects/{pid}/assumptions",
        json={"adders": {"assembly_per_unit": "2.5", "margin_pct": "0.15"}},
    )
    assert updated.status_code == 200
    with_adders = (
        await api_client.get(f"/api/v1/projects/{pid}/impact", params={"volume": 1000})
    ).json()
    assert with_adders["totals"]["adders"]["provenance"] == "CALCULATED"
    assert Decimal(with_adders["totals"]["grand_total"]["value"]) > base_total
