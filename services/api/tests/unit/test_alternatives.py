"""Phase 5: comparator verdicts, numeric grounding, and the approve/reject gate end to end."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.alternatives.comparator import classify, compare
from app.container import Container
from app.domain.enums import CompareResult, FitClass, Lifecycle
from app.domain.grounding import is_grounded, ungrounded_numbers
from app.infra.jobbus import InlineJobBus

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"
HALL = {
    "function": "unipolar switch",
    "output": "open drain",
    "vcc_max_v": 24,
    "package": "SOT-23W",
    "temp_min_c": -40,
    "temp_max_c": 85,
}


# ── comparator ───────────────────────────────────────────────


def test_identical_parameters_are_a_drop_in() -> None:
    comparison = compare("hall_sensor", HALL, None, dict(HALL), "SOT-23W")
    assert all(c.result is CompareResult.MATCH for c in comparison)
    fit, reasons = classify(comparison, "FFF", Lifecycle.ACTIVE)
    assert fit is FitClass.DROP_IN
    assert "footprint is the same" in reasons[0]


def test_better_ratings_are_within_tolerance() -> None:
    can = {
        "standard": "ISO 11898",
        "max_rate_kbps": 1000,
        "package": "SOIC-8",
        "temp_min_c": -40,
        "temp_max_c": 85,
    }
    comparison = compare("can_transceiver", can, None, {**can, "temp_max_c": 125}, "SOIC-8")
    temp = next(c for c in comparison if c.attribute == "temp_max_c")
    assert temp.result is CompareResult.WITHIN_TOLERANCE
    assert classify(comparison, "FFF", Lifecycle.ACTIVE)[0] is FitClass.DROP_IN
    fit, reasons = classify(comparison, "FUNCTIONAL", Lifecycle.ACTIVE)
    assert fit is FitClass.FUNCTIONAL
    assert "functional (not drop-in)" in reasons[-1]


def test_electrical_mismatch_is_not_suitable() -> None:
    a1 = {"gain_v_per_v": 20, "cm_max_v": 80, "package": "TSSOP-8"}
    comparison = compare("current_sense", a1, None, {**a1, "gain_v_per_v": 50}, "TSSOP-8")
    fit, reasons = classify(comparison, "FUNCTIONAL", Lifecycle.ACTIVE)
    assert fit is FitClass.NOT_SUITABLE
    assert reasons == ["gain_v_per_v: 50 vs required 20"]


def test_footprint_change_needs_review_and_lower_ratings_fail() -> None:
    ind = {"inductance_h": 22e-6, "isat_a": 7.0, "package": "12.5x13.5mm"}
    bigger = compare("inductor", ind, None, {**ind, "isat_a": 9.0, "package": "10x11mm"}, "10x11mm")
    assert classify(bigger, "FFF", Lifecycle.ACTIVE)[0] is FitClass.FUNCTIONAL
    weaker = compare("inductor", ind, None, {**ind, "isat_a": 5.0}, "12.5x13.5mm")
    assert classify(weaker, "FFF", Lifecycle.ACTIVE)[0] is FitClass.NOT_SUITABLE


def test_obsolete_candidates_and_unknown_parameters() -> None:
    comparison = compare("hall_sensor", HALL, None, dict(HALL), "SOT-23W")
    assert classify(comparison, "FFF", Lifecycle.OBSOLETE)[0] is FitClass.NOT_SUITABLE
    missing = compare("hall_sensor", HALL, None, {"package": "SOT-23W"}, "SOT-23W")
    fit, reasons = classify(missing, "FFF", Lifecycle.ACTIVE)
    assert fit is FitClass.FUNCTIONAL
    assert any("not published" in r for r in reasons)


# ── grounding ────────────────────────────────────────────────


def test_grounding_rejects_invented_numbers_but_allows_part_numbers() -> None:
    source = "A1120ELHLX-T at USD 0.62/unit, 12,034 in stock, temp_max_c 85"
    assert is_grounded("A1120ELHLX-T costs USD 0.62 with 12034 in stock up to 85 C.", [source])
    assert ungrounded_numbers("It is rated to 150 C and costs 0.62.", [source]) == {"150"}
    assert is_grounded("Use A1120ELHLX-T.", [source])


# ── end to end ───────────────────────────────────────────────


async def _drain(container: Container) -> None:
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()


@pytest.fixture
async def project(api_client: AsyncClient, container: Container) -> dict[str, Any]:
    target = (date.today() + timedelta(days=56)).isoformat()
    pid = (
        await api_client.post(
            "/api/v1/projects",
            json={"name": "MC48", "build_quantities": [100, 1000], "target_ship_date": target},
        )
    ).json()["id"]
    upload = await api_client.post(
        f"/api/v1/projects/{pid}/bom",
        files={"file": ("motor_controller.xlsx", (SAMPLES / "motor_controller.xlsx").read_bytes())},
    )
    await api_client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={"upload_id": upload.json()["upload_id"], "mapping": []},
    )
    await _drain(container)
    lines = (await api_client.get(f"/api/v1/projects/{pid}/lines", params={"limit": 500})).json()[
        "items"
    ]
    return {"pid": pid, "by_mpn": {line["mpn"]: line for line in lines if line["mpn"]}}


async def _investigate(
    client: AsyncClient, container: Container, pid: str, line_id: str
) -> list[dict[str, Any]]:
    job = await client.post(f"/api/v1/projects/{pid}/lines/{line_id}/alternatives/search")
    assert job.status_code == 202
    await _drain(container)
    status = (await client.get(f"/api/v1/jobs/{job.json()['job_id']}")).json()
    assert status["status"] == "SUCCEEDED", status
    items: list[dict[str, Any]] = (
        await client.get(f"/api/v1/projects/{pid}/alternatives", params={"line_id": line_id})
    ).json()["items"]
    return items


async def test_obsolete_part_drop_in_approval_clears_the_blocker(
    api_client: AsyncClient, container: Container, project: dict[str, Any]
) -> None:
    pid, hall = project["pid"], project["by_mpn"]["A1101ELHLT-T"]
    (alt,) = await _investigate(api_client, container, pid, hall["id"])
    assert alt["candidate_mpn"] == "A1120ELHLX-T"
    assert alt["fit_class"] == "DROP_IN"
    assert alt["status"] == "PROPOSED"
    assert alt["delta_cost"]["provenance"] == "UNAVAILABLE"  # the obsolete original has no price
    assert alt["offers_summary"]["authorized_stock"] > 300
    assert "Drop-in replacement for A1101ELHLT-T" in alt["explanation"]
    assert alt["evidence_ids"]

    before = (await api_client.get(f"/api/v1/projects/{pid}/risks")).json()["summary"][
        "open_blockers"
    ]
    decided = await api_client.post(
        f"/api/v1/projects/{pid}/alternatives/{alt['id']}/decision",
        json={"decision": "APPROVE", "note": "Pin-compatible successor; customer agreed"},
        headers={"X-Demo-Role": "ENGINEERING"},
    )
    assert decided.status_code == 200, decided.text
    line = decided.json()["line"]
    assert line["mpn"] == "A1120ELHLX-T"
    assert line["substituted_from"] == "A1101ELHLT-T"
    assert line["selected_offer_id"] is not None
    assert line["overrides"]["mpn"]["by"] == "ENGINEERING"

    risks = (await api_client.get(f"/api/v1/projects/{pid}/risks")).json()
    assert risks["summary"]["open_blockers"] == before - 1
    assert not [r for r in risks["items"] if r["line_id"] == hall["id"] and r["rule_id"] == "L01"]

    detail = (await api_client.get(f"/api/v1/projects/{pid}/lines/{hall['id']}")).json()
    assert detail["alternatives"][0]["status"] == "APPROVED"
    # Re-investigating keeps the decision
    (again,) = await _investigate(api_client, container, pid, hall["id"])
    assert again["status"] == "APPROVED"
    actions = [e.action for e in await container.repos.audit(pid).all()]
    assert actions.count("ALTERNATE_APPROVED") == 1

    # A decision is recorded once: a double click neither re-applies it nor duplicates the audit.
    for decision in ("APPROVE", "REJECT"):
        repeat = await api_client.post(
            f"/api/v1/projects/{pid}/alternatives/{alt['id']}/decision",
            json={"decision": decision, "note": "second click"},
        )
        assert repeat.status_code == 409, decision
    actions = [e.action for e in await container.repos.audit(pid).all()]
    assert actions.count("ALTERNATE_APPROVED") == 1
    assert "ALTERNATE_REJECTED" not in actions


async def test_unsuitable_candidates_cannot_be_approved(
    api_client: AsyncClient, container: Container, project: dict[str, Any]
) -> None:
    pid, ina = project["pid"], project["by_mpn"]["INA240A1PWR"]
    (alt,) = await _investigate(api_client, container, pid, ina["id"])
    assert alt["candidate_mpn"] == "INA240A2PWR"
    assert alt["fit_class"] == "NOT_SUITABLE"
    assert "gain_v_per_v" in alt["explanation"]

    refused = await api_client.post(
        f"/api/v1/projects/{pid}/alternatives/{alt['id']}/decision",
        json={"decision": "APPROVE", "note": "try anyway"},
    )
    assert refused.status_code == 409
    no_note = await api_client.post(
        f"/api/v1/projects/{pid}/alternatives/{alt['id']}/decision",
        json={"decision": "REJECT", "note": ""},
    )
    assert no_note.status_code == 422
    rejected = await api_client.post(
        f"/api/v1/projects/{pid}/alternatives/{alt['id']}/decision",
        json={"decision": "REJECT", "note": "Gain change breaks the shunt design"},
    )
    assert rejected.json()["alternative"]["status"] == "REJECTED"
    rejected_again = await api_client.post(
        f"/api/v1/projects/{pid}/alternatives/{alt['id']}/decision",
        json={"decision": "REJECT", "note": "second click"},
    )
    assert rejected_again.status_code == 409


async def test_functional_alternates_and_parts_without_crossrefs(
    api_client: AsyncClient, container: Container, project: dict[str, Any]
) -> None:
    pid = project["pid"]
    (inductor,) = await _investigate(
        api_client, container, pid, project["by_mpn"]["SRP1265A-220M"]["id"]
    )
    assert inductor["fit_class"] == "FUNCTIONAL"
    assert inductor["delta_cost"]["provenance"] == "CALCULATED"

    job = await api_client.post(
        f"/api/v1/projects/{pid}/lines/{project['by_mpn']['TLV9062IDR']['id']}/alternatives/search"
    )
    await _drain(container)
    status = (await api_client.get(f"/api/v1/jobs/{job.json()['job_id']}")).json()
    assert status["status"] == "SUCCEEDED"
    assert status["warnings"] == ["No known alternates for this part in the catalog"]


async def test_llm_explanations_are_used_only_when_grounded(container: Container) -> None:
    from app.alternatives.graph import InvestigationInput, build_graph
    from app.domain.facts import actual
    from app.domain.models import BomLine, Project

    project_model = Project(id="p", name="P", currency="USD", build_quantities=[100])
    line = BomLine(
        id="ln_1",
        line_no=1,
        mpn="A1101ELHLT-T",
        qty_per=actual(Decimal(3), "ev"),
    )
    data = InvestigationInput(project_model, line, None, None)

    grounded = FakeListChatModel(responses=["A1120ELHLX-T is a drop-in for A1101ELHLT-T."])
    state = await build_graph(container.sourcing.chain, data, grounded)({})
    assert state["alternatives"][0].explanation == "A1120ELHLX-T is a drop-in for A1101ELHLT-T."

    invented = FakeListChatModel(responses=["It survives 999 hours at 150 C."])
    state = await build_graph(container.sourcing.chain, data, invented)({})
    assert "999" not in state["alternatives"][0].explanation  # fell back to the template
