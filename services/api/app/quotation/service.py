"""Quote versions (immutable snapshots) and the finalize gate (human gate 4)."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import DemoRole, ProjectStatus, QuoteStatus, RiskStatus, Severity
from app.domain.errors import ConflictError, QuoteHasOpenBlockersError, ValidationFailedError
from app.domain.facts import Fact, unavailable
from app.domain.ids import new_id
from app.domain.models import (
    AuditEvent,
    QuoteLine,
    QuoteVersion,
    Readiness,
    Risk,
    VolumeQuote,
    quote_version_id,
    utcnow,
)
from app.infra.repositories import OrderBy, Repositories
from app.ingestion.service import ensure_not_busy
from app.risk.engine import UNRESOLVED
from app.risk.service import InsightService


@dataclass
class QuotationService:
    repos: Repositories
    insights: InsightService

    async def create(self, project_id: str, note: str | None, role: DemoRole) -> QuoteVersion:
        data = await self.insights.load(project_id)
        project = data.project
        ensure_not_busy(project)
        if not data.lines:
            raise ValidationFailedError("Upload and analyze a BOM before creating a quote")

        risks = await self.insights.risks(project_id)
        results = {v: self.insights.impact(data, v) for v in project.build_quantities}
        primary = results[project.build_quantities[0]]
        impacts = {i.line_id: i for i in primary.lines}
        offers = data.offers

        existing = await self.repos.quotes(project_id).all()
        version = max((q.version for q in existing), default=0) + 1
        quote = QuoteVersion(
            id=quote_version_id(version),
            version=version,
            created_by=role,
            note=note,
            currency=project.currency,
            data_mode=project.data_mode,
            volumes=[
                VolumeQuote(
                    volume=v,
                    material=r.totals.material,
                    adders=r.totals.adders,
                    total=r.totals.grand_total,
                    per_unit=r.totals.per_unit,
                )
                for v, r in results.items()
            ],
            assumptions=project.assumptions,
            readiness=_readiness(risks),
            unpriced_lines=len(primary.unpriced_line_ids),
            lines=[
                QuoteLine(
                    line_no=line.line_no,
                    cpn=line.cpn,
                    mpn=line.mpn,
                    manufacturer=line.manufacturer,
                    description=line.description,
                    qty_per=line.qty_per,
                    refdes=line.refdes,
                    dnp=line.dnp,
                    substituted_from=line.substituted_from,
                    distributor=offers[line.selected_offer_id].distributor
                    if line.selected_offer_id in offers
                    else None,
                    unit_price=impacts[line.id].unit_price if line.id in impacts else _dnp(),
                    extended=impacts[line.id].extended if line.id in impacts else _dnp(),
                )
                for line in data.lines
            ],
        )
        await self.repos.quotes(project_id).put(quote)
        await self._audit(project_id, role, "QUOTE_CREATED", quote, note)
        return quote

    async def list(self, project_id: str) -> list[QuoteVersion]:
        await self.repos.projects.get(project_id)
        return await self.repos.quotes(project_id).all(order_by=OrderBy("version", descending=True))

    async def get(self, project_id: str, version: int) -> QuoteVersion:
        return await self.repos.quotes(project_id).get(quote_version_id(version))

    async def finalize(
        self, project_id: str, version: int, note: str, role: DemoRole
    ) -> QuoteVersion:
        project = await self.repos.projects.get(project_id)
        quote = await self.get(project_id, version)
        if quote.status is QuoteStatus.FINALIZED:
            raise ConflictError(f"Quote v{version} is already finalized")
        latest = max(q.version for q in await self.repos.quotes(project_id).all())
        if version != latest:
            raise ConflictError(f"Only the latest version (v{latest}) can be finalized")

        current = _readiness(await self.insights.risks(project_id))  # re-check now, not at snapshot
        if not current.ready:
            raise QuoteHasOpenBlockersError(
                f"{len(current.open_blockers)} blocker(s) must be resolved or waived first",
                {"open_blockers": list(current.open_blockers)},
            )
        final = quote.model_copy(
            update={
                "status": QuoteStatus.FINALIZED,
                "finalized_at": utcnow(),
                "finalized_by": role,
                "readiness": current,
                "note": note or quote.note,
            }
        )
        await self.repos.quotes(project_id).put(final)
        project.status = ProjectStatus.FINALIZED
        project.updated_at = utcnow()
        await self.repos.projects.put(project)
        await self._audit(project_id, role, "QUOTE_FINALIZED", final, note)
        return final

    async def reopen(self, project_id: str, reason: str, role: DemoRole) -> None:
        project = await self.repos.projects.get(project_id)
        if project.status is not ProjectStatus.FINALIZED:
            raise ConflictError("Only a finalized project can be reopened")
        project.status = ProjectStatus.IN_REVIEW
        project.updated_at = utcnow()
        await self.repos.projects.put(project)
        await self.insights.refresh(project_id)
        await self.repos.audit(project_id).put(
            AuditEvent(
                id=new_id("aud"),
                actor_role=role,
                action="PROJECT_REOPENED",
                target=f"project:{project_id}",
                reason=reason,
            )
        )

    async def _audit(
        self, project_id: str, role: DemoRole, action: str, quote: QuoteVersion, note: str | None
    ) -> None:
        await self.repos.audit(project_id).put(
            AuditEvent(
                id=new_id("aud"),
                actor_role=role,
                action=action,
                target=f"quote:v{quote.version}",
                after={
                    "ready": quote.readiness.ready,
                    "totals": {str(v.volume): str(v.total.value) for v in quote.volumes},
                },
                reason=note,
            )
        )


def _readiness(risks: list[Risk]) -> Readiness:
    blockers = [r.id for r in risks if r.severity is Severity.BLOCKER and r.status in UNRESOLVED]
    waived = [r.id for r in risks if r.status is RiskStatus.WAIVED]
    return Readiness(ready=not blockers, open_blockers=blockers, waived=waived)


def _dnp() -> Fact[Decimal]:
    return unavailable("Not costed (do not populate)")
