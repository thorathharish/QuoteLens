"""BOM lines: table, detail (offers, component, evidence), MPN correction, offer override."""

from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ContainerDep, DemoRoleDep, ReposDep
from app.api.v1.schemas import LineDetail, LinePage, MpnUpdate, OfferSelection, OffersResponse
from app.domain.enums import IssueCode, MatchStatus
from app.domain.facts import Evidence
from app.domain.models import BomLine
from app.infra.repositories import Filter, OrderBy, Repositories

router = APIRouter(prefix="/projects/{pid}/lines", tags=["lines"])


@router.get("", response_model=LinePage)
async def list_lines(
    pid: str,
    repos: ReposDep,
    issue: IssueCode | None = None,
    match_status: MatchStatus | None = None,
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
    if match_status is not None:
        lines = [line for line in lines if line.match.status is match_status]
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


async def line_detail(repos: Repositories, pid: str, line: BomLine) -> LineDetail:
    offers = (
        await repos.offers(pid).list(filters=[Filter("line_id", "==", line.id)], limit=200)
    ).items
    component = (
        await repos.components(pid).find(line.match.component_id)
        if line.match.component_id
        else None
    )
    wanted = set(line.qty_per.evidence_ids)
    wanted.update(o.evidence_id for o in offers)
    if line.bom_unit_price is not None:
        wanted.update(line.bom_unit_price.evidence_ids)
    if component is not None and component.evidence_id:
        wanted.add(component.evidence_id)
    evidence: dict[str, Evidence] = {}
    for ev_id in sorted(wanted):
        found = await repos.evidence(pid).find(ev_id)
        if found is not None:
            evidence[ev_id] = found
    alternatives = (
        await repos.alternatives(pid).list(filters=[Filter("line_id", "==", line.id)], limit=50)
    ).items
    return LineDetail(
        alternatives=sorted(alternatives, key=lambda a: (a.fit_class.value, a.candidate_mpn)),
        line=line,
        component=component,
        offers=sorted(offers, key=lambda o: (o.distributor, o.sku)),
        selected_offer=next((o for o in offers if o.id == line.selected_offer_id), None),
        recommendation=line.recommendation,
        evidence=evidence,
    )


@router.get("/{lid}", response_model=LineDetail)
async def get_line(pid: str, lid: str, repos: ReposDep) -> LineDetail:
    line = await repos.lines(pid).get(lid)
    return await line_detail(repos, pid, line)


@router.get("/{lid}/offers", response_model=OffersResponse)
async def list_offers(pid: str, lid: str, repos: ReposDep) -> OffersResponse:
    line = await repos.lines(pid).get(lid)
    offers = await repos.offers(pid).list(filters=[Filter("line_id", "==", lid)], limit=200)
    return OffersResponse(
        offers=sorted(offers.items, key=lambda o: (o.distributor, o.sku)),
        recommendation=line.recommendation,
    )


@router.post("/{lid}/match", response_model=LineDetail)
async def set_mpn(
    pid: str, lid: str, body: MpnUpdate, container: ContainerDep, role: DemoRoleDep
) -> LineDetail:
    """Correct the MPN or accept a suggested candidate; the line is re-sourced immediately."""
    line = await container.review.set_mpn(pid, lid, body.mpn, body.manufacturer, body.reason, role)
    return await line_detail(container.repos, pid, line)


@router.put("/{lid}/selected-offer", response_model=LineDetail)
async def select_offer(
    pid: str, lid: str, body: OfferSelection, container: ContainerDep, role: DemoRoleDep
) -> LineDetail:
    line = await container.review.select_offer(pid, lid, body.offer_id, body.reason, role)
    return await line_detail(container.repos, pid, line)
