"""Copilot chat: sessions, history, and grounded answers streamed as Server-Sent Events."""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import ContainerDep
from app.api.ratelimit import RateLimiter, client_key
from app.api.v1.schemas import ChatAsk, ChatHistory, ChatSessionCreate
from app.copilot.service import LLM_UNAVAILABLE
from app.domain.errors import LlmUnavailableError
from app.domain.models import ChatSession

router = APIRouter(prefix="/projects/{pid}/chat", tags=["copilot"])

_limiter = RateLimiter(limit=10, window_seconds=60)


@router.post("/sessions", status_code=201, response_model=ChatSession)
async def create_session(
    pid: str, container: ContainerDep, body: ChatSessionCreate | None = None
) -> ChatSession:
    focus = body or ChatSessionCreate()
    return await container.copilot.create_session(pid, focus.line_id, focus.risk_id)


@router.get("/sessions/{sid}/messages", response_model=ChatHistory)
async def history(pid: str, sid: str, container: ContainerDep) -> ChatHistory:
    return ChatHistory(items=await container.copilot.messages(pid, sid))


@router.post(
    "/sessions/{sid}/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "Events: tool_start, tool_end, token, citations, done, error",
        }
    },
)
async def ask(
    pid: str, sid: str, body: ChatAsk, request: Request, container: ContainerDep
) -> StreamingResponse:
    copilot = container.copilot
    if copilot.model is None:
        raise LlmUnavailableError(LLM_UNAVAILABLE)
    _limiter.check(client_key(request))
    await container.repos.chat_sessions(pid).get(sid)  # 404 before the stream starts

    async def events() -> AsyncIterator[str]:
        try:
            async for kind, payload in copilot.ask(pid, sid, body.content):
                yield _sse(kind, payload)
        except Exception as exc:  # the stream has started: report in-band
            code = getattr(exc, "code", "INTERNAL")
            message = getattr(exc, "message", "The copilot failed to answer")
            yield _sse("error", {"code": code, "message": message})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
