"""Impact + risk use cases over persisted project data.

`refresh` recomputes impact for every build volume and re-evaluates every risk; it runs at
the end of each analysis job and after each user decision that changes line data. Impact
for the UI is computed on demand (cheap and always consistent with current data).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.enums import ProjectStatus
from app.domain.models import BomLine, Component, Offer, Project, Risk, utcnow
from app.impact.engine import LineOverride, compute_project
from app.impact.models import ImpactResult
from app.infra.repositories import Repositories
from app.risk.engine import RiskSummary, carry_decisions, evaluate, summarize


@dataclass
class ProjectData:
    project: Project
    lines: list[BomLine]
    offers: dict[str, Offer]
    components: dict[str, Component]

    @property
    def offers_by_line(self) -> dict[str, list[Offer]]:
        grouped: dict[str, list[Offer]] = defaultdict(list)
        for offer in self.offers.values():
            grouped[offer.line_id].append(offer)
        return grouped


@dataclass
class InsightService:
    repos: Repositories

    async def load(self, project_id: str) -> ProjectData:
        project = await self.repos.projects.get(project_id)
        lines = await self.repos.lines(project_id).all()
        offers = {o.id: o for o in await self.repos.offers(project_id).all()}
        components = {c.id: c for c in await self.repos.components(project_id).all()}
        return ProjectData(
            project, sorted(lines, key=lambda line: line.line_no), offers, components
        )

    @staticmethod
    def impact(
        data: ProjectData, volume: int, overrides: dict[str, LineOverride] | None = None
    ) -> ImpactResult:
        p = data.project
        return compute_project(
            data.lines, data.offers, volume, p.assumptions, p.currency, overrides
        )

    async def risks(self, project_id: str) -> list[Risk]:
        return await self.repos.risks(project_id).all()

    async def refresh(self, project_id: str, today: date | None = None) -> RiskSummary:
        data = await self.load(project_id)
        project = data.project
        primary = self.impact(data, project.build_quantities[0])
        material = primary.totals.material.value
        impacts = {impact.line_id: impact for impact in primary.lines}

        evaluated = evaluate(
            project,
            data.lines,
            data.offers_by_line,
            data.components,
            impacts,
            material,
            today or datetime.now(UTC).date(),
        )
        risk_repo = self.repos.risks(project_id)
        previous = await risk_repo.all()
        risks = carry_decisions(evaluated, previous)
        current = {r.id for r in risks}
        for stale in previous:
            if stale.id not in current:
                await risk_repo.delete(stale.id)
        await risk_repo.put_many(risks)

        summary = self.summary(data, risks, primary)
        totals = {
            v: self.impact(data, v).totals.grand_total.value for v in project.build_quantities
        }
        project.stats.totals_by_volume = {str(v): t for v, t in totals.items() if t is not None}
        project.stats.risks_by_severity = summary.by_severity
        project.stats.open_blockers = summary.open_blockers
        project.stats.spend_at_risk_pct = summary.spend_at_risk_pct.value
        if project.status is not ProjectStatus.FINALIZED:
            project.status = ProjectStatus.QUOTE_READY if summary.ready else ProjectStatus.IN_REVIEW
        project.updated_at = utcnow()
        await self.repos.projects.put(project)
        return summary

    @staticmethod
    def summary(data: ProjectData, risks: list[Risk], primary: ImpactResult) -> RiskSummary:
        costs = {i.line_id: i.extended.value for i in primary.lines if i.extended.value is not None}
        line_costs: dict[str, Decimal] = {k: v for k, v in costs.items() if v is not None}
        costed = sum(1 for line in data.lines if not line.dnp)
        return summarize(risks, costed, line_costs, primary.totals.material.value)
