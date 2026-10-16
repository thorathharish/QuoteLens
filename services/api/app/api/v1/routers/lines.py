"""BOM lines table (read side). Phase 3 adds line detail, offers and corrections."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ReposDep
from app.api.v1.schemas import LinePage
from app.domain.enums import IssueCode
from app.infra.repositories import OrderBy

router = APIRouter(prefix="/projects/{pid}/lines", tags=["lines"])


@router.get("", response_model=LinePage)
async def list_lines(
    pid: str,
    repos: ReposDep,
    issue: IssueCode | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: Annotated[str | None, Query(pattern=r"^\d+$")] = None,
) -> LinePage:
    await repos.projects.get(pid)
    # A BOM is bounded (≤ a few thousand lines): filter in memory, then page by offset.
    lines = await repos.lines(pid).all(order_by=OrderBy("line_no"))
    counts = Counter(i.code.value for line in lines for i in line.validation)
    if issue is not None:
        lines = [line for line in lines if any(i.code is issue for i in line.validation)]
    if q:
        needle = q.casefold()
        lines = [
            line
            for line in lines
            if any(
                needle in (v or "").casefold()
                for v in (
                    line.mpn,
                    line.manufacturer,
                    line.description,
                    line.cpn,
                    ",".join(line.refdes),
                )
            )
        ]
    start = int(cursor or 0)
    page = lines[start : start + limit]
    more = start + limit < len(lines)
    return LinePage(
        items=page, issue_counts=dict(counts), next_cursor=str(start + limit) if more else None
    )
