"""Copilot: tool loop, numeric grounding, citation filtering, budget and failure modes.

A scripted chat model replays planned AI messages (tool calls, then answers), so these tests
exercise the real graph, tools and grounding logic without calling Gemini.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.api.ratelimit import RateLimiter
from app.config import Settings
from app.container import Container, build_container
from app.domain.errors import RateLimitedError
from app.infra.jobbus import InlineJobBus
from app.infra.repositories.memory import InMemoryDocumentStore
from app.main_api import create_app
from app.sourcing.service import component_evidence_id

SAMPLES = Path(__file__).resolve().parents[4] / "data" / "samples"
HALL_EVIDENCE = component_evidence_id("A1101ELHLT-T")


class ScriptedModel(BaseChatModel):
    script: list[AIMessage]
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":  # type: ignore[override]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        reply = (
            self.script.pop(0)
            if self.script
            else AIMessage(content="Not available in project data.")
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name: str, args: dict[str, Any], call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


async def _client(
    model: BaseChatModel | None, max_tool_calls: int = 6
) -> tuple[AsyncClient, Container]:
    settings = Settings(
        env="test", llm_enabled=False, copilot_max_tool_calls=max_tool_calls, _env_file=None
    )  # type: ignore[call-arg]
    container = build_container(settings, store=InMemoryDocumentStore(), copilot_model=model)
    if model is None:
        container.copilot.model = None
    client = AsyncClient(transport=ASGITransport(app=create_app(container)), base_url="http://test")
    return client, container


async def _project_with_session(client: AsyncClient, container: Container) -> tuple[str, str]:
    pid = (
        await client.post("/api/v1/projects", json={"name": "MC48", "build_quantities": [100]})
    ).json()["id"]
    upload = await client.post(
        f"/api/v1/projects/{pid}/bom",
        files={"file": ("motor_controller.xlsx", (SAMPLES / "motor_controller.xlsx").read_bytes())},
    )
    await client.put(
        f"/api/v1/projects/{pid}/bom/mapping",
        json={"upload_id": upload.json()["upload_id"], "mapping": []},
    )
    assert isinstance(container.job_bus, InlineJobBus)
    await container.job_bus.drain()
    sid = (await client.post(f"/api/v1/projects/{pid}/chat/sessions", json={})).json()["id"]
    return pid, sid


async def _ask(
    client: AsyncClient, pid: str, sid: str, question: str
) -> list[tuple[str, dict[str, Any]]]:
    response = await client.post(
        f"/api/v1/projects/{pid}/chat/sessions/{sid}/messages", json={"content": question}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for block in response.text.strip().split("\n\n"):
        kind, data = block.split("\n", 1)
        events.append((kind.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def _answer(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(e["text"] for k, e in events if k == "token")


@pytest.fixture
async def grounded() -> AsyncIterator[tuple[AsyncClient, Container, ScriptedModel]]:
    model = ScriptedModel(
        script=[
            call("get_line", {"line": "A1101ELHLT-T"}),
            AIMessage(
                content=f"A1101ELHLT-T is OBSOLETE and authorized stock is 0 [E:{HALL_EVIDENCE}]."
            ),
        ]
    )
    client, container = await _client(model)
    async with client:
        yield client, container, model


async def test_grounded_answer_streams_tools_tokens_citations(
    grounded: tuple[AsyncClient, Container, ScriptedModel],
) -> None:
    client, container, model = grounded
    pid, sid = await _project_with_session(client, container)
    events = await _ask(client, pid, sid, "Why is the hall sensor a blocker?")
    kinds = [k for k, _ in events]
    assert kinds[0] == "tool_start"
    assert events[0][1]["name"] == "get_line"
    assert "tool_end" in kinds
    assert kinds[-2:] == ["citations", "done"]
    assert _answer(events).startswith("A1101ELHLT-T is OBSOLETE")
    (citation,) = dict(events)["citations"]["items"]
    assert citation["evidence_id"] == HALL_EVIDENCE
    assert "demo catalog" in citation["label"]
    assert dict(events)["done"]["grounded"] is True

    # The tool result the model saw contains the real lifecycle data
    tool_output = model.seen[-1][-1].content
    assert "OBSOLETE" in str(tool_output)

    history = (await client.get(f"/api/v1/projects/{pid}/chat/sessions/{sid}/messages")).json()[
        "items"
    ]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["tool_calls"][0]["name"] == "get_line"


async def test_invented_numbers_are_corrected_or_flagged() -> None:
    corrected_model = ScriptedModel(
        script=[
            call("get_project_summary", {}),
            AIMessage(content="The total is USD 99,999.99."),
            AIMessage(content="Not available in project data."),
        ]
    )
    client, container = await _client(corrected_model)
    async with client:
        pid, sid = await _project_with_session(client, container)
        events = await _ask(client, pid, sid, "What is the total?")
        assert _answer(events) == "Not available in project data."
        assert dict(events)["done"]["grounded"] is True

    stubborn = ScriptedModel(
        script=[
            call("get_project_summary", {}),
            AIMessage(content="The total is USD 99,999.99."),
            AIMessage(content="Still USD 99,999.99."),
        ]
    )
    client, container = await _client(stubborn)
    async with client:
        pid, sid = await _project_with_session(client, container)
        done = dict(await _ask(client, pid, sid, "What is the total?"))["done"]
        assert done["grounded"] is False
        assert done["unverified_numbers"] == ["99999.99"]


async def test_fabricated_citations_are_dropped_and_budget_is_enforced() -> None:
    model = ScriptedModel(
        script=[
            call("list_risks", {"severity": "BLOCKER"}, "c1"),
            call("search_lines", {"query": "fuse"}, "c2"),  # exceeds the budget of 1 → finalize
            AIMessage(content="There are blockers [E:ev_made_up]."),
        ]
    )
    client, container = await _client(model, max_tool_calls=1)
    async with client:
        pid, sid = await _project_with_session(client, container)
        events = await _ask(client, pid, sid, "List blockers")
        assert [e["name"] for k, e in events if k == "tool_start"] == ["list_risks", "search_lines"]
        assert len([k for k, _ in events if k == "tool_end"]) == 1  # second call never ran
        assert dict(events)["citations"]["items"] == []


async def test_bad_tool_arguments_do_not_end_the_conversation() -> None:
    model = ScriptedModel(
        script=[
            call("get_impact", {"volume": -5}),
            AIMessage(content="Not available in project data."),
        ]
    )
    client, container = await _client(model)
    async with client:
        pid, sid = await _project_with_session(client, container)
        events = await _ask(client, pid, sid, "Impact at -5?")
        assert dict(events)["done"]["grounded"] is True
        assert "error" in str(model.seen[-1][-1].content)


async def test_copilot_unavailable_without_a_model_and_unknown_session() -> None:
    client, _ = await _client(None)
    async with client:
        pid = (
            await client.post("/api/v1/projects", json={"name": "P", "build_quantities": [1]})
        ).json()["id"]
        sid = (await client.post(f"/api/v1/projects/{pid}/chat/sessions")).json()["id"]
        response = await client.post(
            f"/api/v1/projects/{pid}/chat/sessions/{sid}/messages", json={"content": "hi"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LLM_UNAVAILABLE"

    client, _ = await _client(ScriptedModel(script=[]))
    async with client:
        pid = (
            await client.post("/api/v1/projects", json={"name": "P", "build_quantities": [1]})
        ).json()["id"]
        missing = await client.post(
            f"/api/v1/projects/{pid}/chat/sessions/chat_nope/messages", json={"content": "hi"}
        )
        assert missing.status_code == 404


def test_rate_limiter_blocks_bursts() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")
    with pytest.raises(RateLimitedError):
        limiter.check("1.2.3.4")
    limiter.check("5.6.7.8")  # other clients are unaffected


async def test_every_tool_returns_json_with_evidence(
    grounded: tuple[AsyncClient, Container, ScriptedModel],
) -> None:
    from app.copilot.tools import ToolRun, build_tools

    client, container, _ = grounded
    pid, _sid = await _project_with_session(client, container)
    run = ToolRun()
    tools = {t.name: t for t in build_tools(pid, container.repos, container.insights, run)}
    calls = {
        "get_project_summary": {},
        "search_lines": {"query": "yageo", "only_risky": False},
        "get_line": {"line": "DRV8323RSRGZR"},
        "get_offers": {"line": "INA240A1PWR"},
        "list_risks": {"severity": "BLOCKER"},
        "get_impact": {"volume": 1000},
        "simulate": {"volume": 100, "overrides": [{"line": "SRP1265A-220M", "scrap_pct": "0"}]},
        "get_evidence": {"evidence_id": HALL_EVIDENCE},
    }
    assert set(calls) == set(tools)
    for name, args in calls.items():
        payload = json.loads(await tools[name].ainvoke(args))
        assert "error" not in payload, (name, payload)
        assert "evidence_ids" in payload
    line_trace = json.loads(
        await tools["get_impact"].ainvoke({"volume": 100, "line": "SRP1265A-220M"})
    )
    assert line_trace["trace"][0]["step"] == "Required"
    missing = json.loads(await tools["get_line"].ainvoke({"line": "NOPE-123"}))
    assert missing["error"].startswith("No line matches")
    assert HALL_EVIDENCE in run.evidence_ids


async def test_search_lines_finds_data_problems_and_rejects_unknown_codes(
    grounded: tuple[AsyncClient, Container, ScriptedModel],
) -> None:
    from app.copilot.tools import ToolRun, build_tools

    client, container, _ = grounded
    pid, _sid = await _project_with_session(client, container)
    tools = {t.name: t for t in build_tools(pid, container.repos, container.insights, ToolRun())}
    search = tools["search_lines"]

    problems = json.loads(await search.ainvoke({"has_issues": True}))
    codes = {c.split(":")[0] for issues in problems["issue_details"].values() for c in issues}
    assert problems["count"] >= 2
    assert {"MISSING_MPN", "QTY_INVALID"} <= codes

    missing = json.loads(await search.ainvoke({"issue": "missing_mpn"}))
    assert missing["count"] >= 1

    unknown = json.loads(await search.ainvoke({"issue": "DATA_PROBLEM"}))
    assert "error" in unknown
    assert "MISSING_MPN" in unknown["valid_issue_codes"]


def test_cited_ids_reads_single_and_grouped_citations() -> None:
    from app.copilot.service import cited_ids

    answer = (
        "Short by 52 [E:ev_off_a, E:ev_off_b]. Lead 112 d [E:ev_off_c,ev_off_a]. "
        "Needed 101 [E:ev_bom_r1]. Not a citation: [E:bad id!]."
    )
    assert cited_ids(answer) == ["ev_off_a", "ev_off_b", "ev_off_c", "ev_bom_r1"]
