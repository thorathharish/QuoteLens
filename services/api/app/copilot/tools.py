"""Copilot tools: read-only views of one project's data (plus a non-persistent what-if).

Every tool returns compact JSON with an `evidence_ids` list. The answer may only cite
those ids and may only state numbers that appear in these outputs (grounding check).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.enums import RiskCategory, RiskStatus, Severity
from app.domain.facts import Fact
from app.domain.models import BomLine, Offer, Risk
from app.impact.engine import LineOverride
from app.infra.repositories import Repositories
from app.risk.engine import UNRESOLVED, sort_risks
from app.risk.service import InsightService, ProjectData

MAX_ROWS = 25


def _fact(fact: Fact[Decimal] | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    out: dict[str, Any] = {
        "value": None if fact.value is None else str(fact.value),
        "provenance": fact.provenance.value,
    }
    if fact.note:
        out["note"] = fact.note
    if fact.formula:
        out["formula"] = fact.formula
    return out


def _line_brief(line: BomLine, offers: dict[str, Offer]) -> dict[str, Any]:
    offer = offers.get(line.selected_offer_id or "")
    return {
        "line_id": line.id,
        "line_no": line.line_no,
        "mpn": line.mpn,
        "manufacturer": line.manufacturer,
        "description": line.description,
        "refdes": ",".join(line.refdes[:12]),
        "qty_per": _fact(line.qty_per),
        "dnp": line.dnp,
        "match": line.match.status.value,
        "selected_distributor": offer.distributor if offer else None,
        "substituted_from": line.substituted_from,
        "issues": [i.code.value for i in line.validation],
    }


def _risk_brief(risk: Risk) -> dict[str, Any]:
    return {
        "risk_id": risk.id,
        "line_id": risk.line_id,
        "rule": risk.rule_id,
        "severity": risk.severity.value,
        "status": risk.status.value,
        "title": risk.title,
        "why": risk.why,
        "actions": [a.label for a in risk.suggested_actions],
    }


@dataclass
class ToolRun:
    """Collects evidence ids and raw outputs produced during one copilot turn."""

    evidence_ids: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def record(self, payload: dict[str, Any]) -> str:
        ids = [e for e in payload.get("evidence_ids", []) if e]
        self.evidence_ids.extend(e for e in ids if e not in self.evidence_ids)
        text = json.dumps(payload, default=str)
        self.outputs.append(text)
        return text


class SearchArgs(BaseModel):
    query: str | None = Field(
        default=None, description="Text in MPN, manufacturer, description or refdes"
    )
    issue: str | None = Field(default=None, description="Data issue code, e.g. MISSING_MPN")
    only_risky: bool = Field(default=False, description="Only lines with unresolved risks")


class LineArgs(BaseModel):
    line: str = Field(description="Line id (ln_...) or MPN")


class RiskArgs(BaseModel):
    severity: Severity | None = None
    category: RiskCategory | None = None
    status: RiskStatus | None = None


class ImpactArgs(BaseModel):
    volume: int | None = Field(default=None, ge=1, description="Build quantity; default primary")
    line: str | None = Field(default=None, description="Optional line id or MPN for one line")


class OverrideArg(BaseModel):
    line: str = Field(description="Line id or MPN")
    scrap_pct: Decimal | None = Field(default=None, ge=0, le=1)
    qty_per: Decimal | None = Field(default=None, gt=0)
    on_hand: int | None = Field(default=None, ge=0)
    offer_id: str | None = None


class SimulateArgs(BaseModel):
    volume: int = Field(ge=1)
    overrides: list[OverrideArg] = Field(default=[])


class EvidenceArgs(BaseModel):
    evidence_id: str


class EmptyArgs(BaseModel):
    pass


def build_tools(
    project_id: str, repos: Repositories, insights: InsightService, run: ToolRun
) -> list[StructuredTool]:
    cache: dict[str, ProjectData] = {}

    async def data() -> ProjectData:
        if "d" not in cache:
            cache["d"] = await insights.load(project_id)
        return cache["d"]

    def resolve(d: ProjectData, ref: str) -> BomLine | None:
        ref_norm = ref.strip().upper()
        return next(
            (
                line
                for line in d.lines
                if line.id == ref.strip()
                or (line.mpn or "") == ref_norm
                or (line.substituted_from or "") == ref_norm
            ),
            None,
        )

    async def project_summary() -> str:
        d = await data()
        risks = await insights.risks(project_id)
        primary = insights.impact(d, d.project.build_quantities[0])
        summary = insights.summary(d, risks, primary)
        totals = {
            str(v): _fact(insights.impact(d, v).totals.grand_total)
            for v in d.project.build_quantities
        }
        return run.record(
            {
                "project": d.project.name,
                "status": d.project.status.value,
                "currency": d.project.currency,
                "build_quantities": d.project.build_quantities,
                "data_mode": d.project.data_mode.value,
                "target_ship_date": str(d.project.target_ship_date)
                if d.project.target_ship_date
                else None,
                "lines": len(d.lines),
                "unpriced_lines": len(primary.unpriced_line_ids),
                "totals_by_volume": totals,
                "open_blockers": summary.open_blockers,
                "ready_to_quote": summary.ready,
                "risks_by_severity": {k.value: v for k, v in summary.by_severity.items()},
                "readiness_pct": _fact(summary.readiness_pct),
                "spend_at_risk_pct": _fact(summary.spend_at_risk_pct),
                "evidence_ids": [],
            }
        )

    async def search_lines(
        query: str | None = None, issue: str | None = None, only_risky: bool = False
    ) -> str:
        d = await data()
        risky = {r.line_id for r in await insights.risks(project_id) if r.status in UNRESOLVED}
        rows = [
            line
            for line in d.lines
            if (
                not query
                or query.casefold()
                in " ".join(
                    filter(
                        None, [line.mpn, line.manufacturer, line.description, ",".join(line.refdes)]
                    )
                ).casefold()
            )
            and (not issue or any(i.code.value == issue.upper() for i in line.validation))
            and (not only_risky or line.id in risky)
        ]
        return run.record(
            {
                "count": len(rows),
                "lines": [_line_brief(x, d.offers) for x in rows[:MAX_ROWS]],
                "truncated": len(rows) > MAX_ROWS,
                "evidence_ids": [e for x in rows[:MAX_ROWS] for e in x.qty_per.evidence_ids],
            }
        )

    async def get_line(line: str) -> str:
        d = await data()
        found = resolve(d, line)
        if found is None:
            return run.record({"error": f"No line matches '{line}'", "evidence_ids": []})
        offers = [o for o in d.offers.values() if o.line_id == found.id]
        risks = [r for r in await insights.risks(project_id) if r.line_id == found.id]
        component = d.components.get(found.match.component_id or "")
        impact = next(
            (
                i
                for i in insights.impact(d, d.project.build_quantities[0]).lines
                if i.line_id == found.id
            ),
            None,
        )
        alternatives = [
            a for a in await repos.alternatives(project_id).all() if a.line_id == found.id
        ]
        return run.record(
            {
                "line": _line_brief(found, d.offers),
                "component": None
                if component is None
                else {
                    "manufacturer": component.manufacturer,
                    "category": component.category,
                    "lifecycle": component.lifecycle.value,
                    "ltb_date": str(component.ltb_date) if component.ltb_date else None,
                },
                "recommendation": found.recommendation.model_dump(mode="json")
                if found.recommendation
                else None,
                "impact_at_primary_volume": None
                if impact is None
                else {
                    "volume": impact.volume,
                    "buy_qty": _fact(impact.buy_qty),
                    "unit_price": _fact(impact.unit_price),
                    "extended": _fact(impact.extended),
                    "excess_cost": _fact(impact.excess_cost),
                    "shortage_qty": _fact(impact.shortage_qty),
                },
                "risks": [_risk_brief(r) for r in sort_risks(risks)],
                "alternatives": [
                    {
                        "candidate": a.candidate_mpn,
                        "fit": a.fit_class.value,
                        "status": a.status.value,
                        "explanation": a.explanation,
                    }
                    for a in alternatives
                ],
                "evidence_ids": [
                    *found.qty_per.evidence_ids,
                    *(o.evidence_id for o in offers),
                    *(r for risk in risks for r in risk.evidence_ids),
                    component.evidence_id if component and component.evidence_id else "",
                ],
            }
        )

    async def get_offers(line: str) -> str:
        d = await data()
        found = resolve(d, line)
        if found is None:
            return run.record({"error": f"No line matches '{line}'", "evidence_ids": []})
        offers = sorted(
            (o for o in d.offers.values() if o.line_id == found.id), key=lambda o: o.distributor
        )
        return run.record(
            {
                "mpn": found.mpn,
                "selected_offer_id": found.selected_offer_id,
                "offers": [
                    {
                        "offer_id": o.id,
                        "distributor": o.distributor,
                        "authorized": o.authorized,
                        "stock": o.stock,
                        "moq": o.moq,
                        "multiple": o.order_multiple,
                        "lead_time_days": o.lead_time_days,
                        "lifecycle": o.lifecycle.value,
                        "currency": o.currency,
                        "mode": o.mode.value,
                        "price_breaks": [
                            {"qty": b.qty, "unit_price": str(b.unit_price)} for b in o.price_breaks
                        ],
                        "evidence_id": o.evidence_id,
                    }
                    for o in offers
                ],
                "evidence_ids": [o.evidence_id for o in offers],
            }
        )

    async def list_risks(
        severity: Severity | None = None,
        category: RiskCategory | None = None,
        status: RiskStatus | None = None,
    ) -> str:
        d = await data()
        risks = sort_risks(
            [
                r
                for r in await insights.risks(project_id)
                if (severity is None or r.severity is severity)
                and (category is None or r.category is category)
                and (status is None or r.status is status)
            ]
        )
        mpn = {
            line.id: line.mpn or (line.refdes[0] if line.refdes else line.id) for line in d.lines
        }
        return run.record(
            {
                "count": len(risks),
                "risks": [
                    {**_risk_brief(r), "part": mpn.get(r.line_id or "")} for r in risks[:MAX_ROWS]
                ],
                "evidence_ids": [e for r in risks[:MAX_ROWS] for e in r.evidence_ids],
            }
        )

    async def get_impact(volume: int | None = None, line: str | None = None) -> str:
        d = await data()
        result = insights.impact(d, volume or d.project.build_quantities[0])
        if line:
            found = resolve(d, line)
            impact = next((i for i in result.lines if found and i.line_id == found.id), None)
            if impact is None:
                return run.record({"error": f"No priced line matches '{line}'", "evidence_ids": []})
            return run.record(
                {
                    "volume": result.volume,
                    "mpn": found.mpn if found else None,
                    "trace": [
                        {"step": s.label, "formula": s.formula, "output": _fact(s.output)}
                        for s in impact.trace
                    ],
                    "evidence_ids": [e for s in impact.trace for e in s.output.evidence_ids],
                }
            )
        t = result.totals
        return run.record(
            {
                "volume": result.volume,
                "currency": result.currency,
                "totals": {
                    "required_material": _fact(t.required_material),
                    "scrap_cost": _fact(t.scrap_cost),
                    "excess_cost": _fact(t.excess_cost),
                    "material": _fact(t.material),
                    "adders": _fact(t.adders),
                    "grand_total": _fact(t.grand_total),
                    "per_unit": _fact(t.per_unit),
                },
                "unpriced_lines": len(result.unpriced_line_ids),
                "top_savings": [
                    {"line_id": r.line_id, "message": r.message, "saving": _fact(r.saving)}
                    for r in result.recommendations[:5]
                ],
                "evidence_ids": [
                    e for r in result.recommendations[:5] for e in r.saving.evidence_ids
                ],
            }
        )

    async def simulate(volume: int, overrides: list[OverrideArg] | None = None) -> str:
        d = await data()
        mapped: dict[str, LineOverride] = {}
        for o in overrides or []:
            found = resolve(d, o.line)
            if found is None:
                return run.record({"error": f"No line matches '{o.line}'", "evidence_ids": []})
            mapped[found.id] = LineOverride(
                scrap_pct=o.scrap_pct, qty_per=o.qty_per, on_hand=o.on_hand, offer_id=o.offer_id
            )
        base = insights.impact(d, volume).totals.grand_total
        sim = insights.impact(d, volume, mapped).totals.grand_total
        delta = (
            str(sim.value - base.value)
            if sim.value is not None and base.value is not None
            else None
        )
        return run.record(
            {
                "volume": volume,
                "what_if_only": True,
                "baseline_total": _fact(base),
                "simulated_total": _fact(sim),
                "delta": delta,
                "evidence_ids": [],
            }
        )

    async def get_evidence(evidence_id: str) -> str:
        evidence = await repos.evidence(project_id).find(evidence_id)
        if evidence is None:
            return run.record({"error": f"Unknown evidence id {evidence_id}", "evidence_ids": []})
        return run.record({**evidence.model_dump(mode="json"), "evidence_ids": [evidence.id]})

    def tool(
        fn: Callable[..., Awaitable[str]], name: str, description: str, args: type[BaseModel]
    ) -> StructuredTool:
        return StructuredTool.from_function(
            coroutine=fn, name=name, description=description, args_schema=args
        )

    return [
        tool(
            project_summary,
            "get_project_summary",
            "Project status, totals per build volume, readiness and risk counts.",
            EmptyArgs,
        ),
        tool(
            search_lines,
            "search_lines",
            "Find BOM lines by text, data issue, or unresolved risk.",
            SearchArgs,
        ),
        tool(
            get_line,
            "get_line",
            "Everything about one line: component, lifecycle, recommended offer and reasons, "
            "cost at the primary volume, risks and alternatives.",
            LineArgs,
        ),
        tool(
            get_offers,
            "get_offers",
            "All distributor offers for a line with price breaks, stock, MOQ, lead time.",
            LineArgs,
        ),
        tool(
            list_risks,
            "list_risks",
            "Explained risks, optionally filtered by severity, category or status.",
            RiskArgs,
        ),
        tool(
            get_impact,
            "get_impact",
            "Cost impact for a build volume (totals, scrap, MOQ excess, savings) "
            "or one line's calculation trace.",
            ImpactArgs,
        ),
        tool(
            simulate,
            "simulate",
            "What-if cost for a volume with optional per-line changes. Never saved.",
            SimulateArgs,
        ),
        tool(
            get_evidence, "get_evidence", "The source record behind an evidence id.", EvidenceArgs
        ),
    ]
