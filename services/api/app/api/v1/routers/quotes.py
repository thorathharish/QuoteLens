"""Quote versions, finalize (human gate 4), XLSX export, and reopening for a new revision."""

import re
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import ContainerDep, DemoRoleDep
from app.api.v1.schemas import QuoteCreate, QuoteFinalize, QuoteList, ReopenRequest
from app.domain.models import QuoteVersion
from app.quotation.export_xlsx import build_workbook
from app.risk.engine import sort_risks

router = APIRouter(prefix="/projects/{pid}", tags=["quotes"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/quotes", status_code=201, response_model=QuoteVersion)
async def create_quote(
    pid: str, container: ContainerDep, role: DemoRoleDep, body: QuoteCreate | None = None
) -> QuoteVersion:
    return await container.quotes.create(pid, body.note if body else None, role)


@router.get("/quotes", response_model=QuoteList)
async def list_quotes(pid: str, container: ContainerDep) -> QuoteList:
    return QuoteList(items=await container.quotes.list(pid))


@router.get("/quotes/{version}", response_model=QuoteVersion)
async def get_quote(pid: str, version: int, container: ContainerDep) -> QuoteVersion:
    return await container.quotes.get(pid, version)


@router.post("/quotes/{version}/finalize", response_model=QuoteVersion)
async def finalize_quote(
    pid: str, version: int, body: QuoteFinalize, container: ContainerDep, role: DemoRoleDep
) -> QuoteVersion:
    return await container.quotes.finalize(pid, version, body.note, role)


@router.get(
    "/quotes/{version}/export",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "Quote workbook"}},
)
async def export_quote(
    pid: str,
    version: int,
    container: ContainerDep,
    file_format: Annotated[str, Query(alias="format", pattern="^xlsx$")] = "xlsx",
) -> Response:
    project = await container.repos.projects.get(pid)
    quote = await container.quotes.get(pid, version)
    risks = sort_risks(await container.insights.risks(pid))
    data = build_workbook(project, quote, risks)
    # Keep a copy for traceability; the bucket deletes exports/ after 7 days (free tier).
    await container.blobs.put(f"exports/{pid}/quote-v{version}.{file_format}", data, XLSX)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", project.name)[:40].strip("-") or "quote"
    disposition = f'attachment; filename="{safe}-v{version}.xlsx"'
    return Response(content=data, media_type=XLSX, headers={"Content-Disposition": disposition})


@router.post("/reopen", status_code=204)
async def reopen(
    pid: str, body: ReopenRequest, container: ContainerDep, role: DemoRoleDep
) -> Response:
    await container.quotes.reopen(pid, body.reason, role)
    return Response(status_code=204)
