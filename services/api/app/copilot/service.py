"""Copilot use case: one grounded answer per question, streamed as events.

Order of operations for a question:
1. Run the agent (tool events stream as they happen).
2. Grounding check: every number in the answer must appear in this turn's tool outputs
   (or the question). Otherwise the model gets one correction attempt; if it still fails,
   the answer is delivered with grounded=false so the UI can flag it.
3. Citations keep only [E:id] markers whose ids the tools actually returned.
4. Only then is the answer streamed as tokens. Unverified numbers never flash on screen.
"""

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.copilot.agent import SYSTEM_PROMPT, build_agent, stream_agent
from app.copilot.tools import ToolRun, build_tools
from app.domain.enums import ChatRole
from app.domain.errors import LlmUnavailableError
from app.domain.grounding import ungrounded_numbers
from app.domain.ids import new_id
from app.domain.models import ChatMessage, ChatSession, Citation, ToolCall
from app.infra.repositories import OrderBy, Repositories
from app.risk.service import InsightService

# One id per bracket, or several: [E:ev_a] and [E:ev_a, E:ev_b] (or [E:ev_a, ev_b]).
_CITATION_GROUP = re.compile(r"\[E:([^\]]+)\]")
_CITATION_ID = re.compile(r"(?:E:)?([A-Za-z0-9_\-]+)")


def cited_ids(answer: str) -> list[str]:
    """Evidence ids cited in an answer, in order of first mention."""
    ids = (
        match.group(1)
        for group in _CITATION_GROUP.findall(answer)
        for part in group.split(",")
        if (match := _CITATION_ID.fullmatch(part.strip()))
    )
    return list(dict.fromkeys(ids))


HISTORY_TURNS = 6
TOKEN_CHUNK = 24
LLM_UNAVAILABLE = (
    "The copilot needs an LLM: Gemini on Vertex AI (GCP_PROJECT) or OpenRouter "
    "(LLM_PROVIDER=openrouter and OPENROUTER_API_KEY), with LLM_ENABLED=true."
)


@dataclass
class CopilotService:
    repos: Repositories
    insights: InsightService
    model: BaseChatModel | None
    max_tool_calls: int = 6

    async def create_session(
        self, project_id: str, line_id: str | None, risk_id: str | None
    ) -> ChatSession:
        await self.repos.projects.get(project_id)
        session = ChatSession(id=new_id("chat"), focus_line_id=line_id, focus_risk_id=risk_id)
        await self.repos.chat_sessions(project_id).put(session)
        return session

    async def messages(self, project_id: str, session_id: str) -> list[ChatMessage]:
        await self.repos.chat_sessions(project_id).get(session_id)
        return await self.repos.chat_messages(project_id, session_id).all(
            order_by=OrderBy("created_at")
        )

    async def ask(
        self, project_id: str, session_id: str, question: str
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        if self.model is None:
            raise LlmUnavailableError(LLM_UNAVAILABLE)
        session = await self.repos.chat_sessions(project_id).get(session_id)
        store = self.repos.chat_messages(project_id, session_id)
        history = await self._history(project_id, session_id)
        focus = _focus_note(session)

        await store.put(ChatMessage(id=new_id("msg"), role=ChatRole.USER, content=question))
        run = ToolRun()
        tools = build_tools(project_id, self.repos, self.insights, run)
        agent = build_agent(self.model, tools, self.max_tool_calls)

        calls: list[ToolCall] = []
        answer = ""
        async for kind, payload in stream_agent(agent, history, focus + question):
            if kind == "tool_start":
                calls.append(ToolCall(name=payload["name"], args=payload["args"]))
                yield "tool_start", payload
            elif kind == "tool_end":
                yield "tool_end", payload
            else:
                answer = payload["text"]

        sources = [*run.outputs, question, focus]
        missing = ungrounded_numbers(answer, sources)
        if missing:
            answer = await self._correct(question, run, answer, missing)
            missing = ungrounded_numbers(answer, sources)
        grounded = not missing and bool(answer)
        if not answer:
            answer = "Not available in project data."

        citations = await self._citations(project_id, answer, run)
        for start in range(0, len(answer), TOKEN_CHUNK):
            yield "token", {"text": answer[start : start + TOKEN_CHUNK]}
        yield "citations", {"items": [c.model_dump() for c in citations]}

        message = ChatMessage(
            id=new_id("msg"),
            role=ChatRole.ASSISTANT,
            content=answer,
            citations=citations,
            tool_calls=calls,
            grounded=grounded,
        )
        await store.put(message)
        yield (
            "done",
            {"message_id": message.id, "grounded": grounded, "unverified_numbers": sorted(missing)},
        )

    async def _correct(self, question: str, run: ToolRun, answer: str, missing: set[str]) -> str:
        assert self.model is not None
        correction = (
            "Your answer contained numbers not present in the tool results: "
            f"{', '.join(sorted(missing))}. Rewrite it using only numbers that appear in these "
            "results, keeping [E:id] citations.\n\n"
            "Tool results:\n" + "\n".join(run.outputs)[:12000]
        )
        reply = await self.model.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=question),
                AIMessage(content=answer),
                HumanMessage(content=correction),
            ]
        )
        content = reply.content
        return content.strip() if isinstance(content, str) else str(content)

    async def _citations(self, project_id: str, answer: str, run: ToolRun) -> list[Citation]:
        cited = [ev for ev in cited_ids(answer) if ev in run.evidence_ids]
        citations: list[Citation] = []
        for ev_id in cited:
            evidence = await self.repos.evidence(project_id).find(ev_id)
            if evidence is not None:
                label = evidence.source_name + (
                    f" · {evidence.source_ref}" if evidence.source_ref else ""
                )
                citations.append(Citation(evidence_id=ev_id, label=label))
        return citations

    async def _history(self, project_id: str, session_id: str) -> list[BaseMessage]:
        previous = await self.repos.chat_messages(project_id, session_id).all(
            order_by=OrderBy("created_at")
        )
        recent = previous[-HISTORY_TURNS * 2 :]
        return [
            HumanMessage(content=m.content)
            if m.role is ChatRole.USER
            else AIMessage(content=m.content)
            for m in recent
        ]


def _focus_note(session: ChatSession) -> str:
    if session.focus_line_id:
        return f"(Context: the user is looking at line {session.focus_line_id}.) "
    if session.focus_risk_id:
        return f"(Context: the user is looking at risk {session.focus_risk_id}.) "
    return ""
