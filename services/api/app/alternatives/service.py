"""Alternative-part use cases: investigate (propose) and decide (human gate 3).

Approving creates a new line version that records the original part (`substituted_from`),
re-sources the line and re-evaluates risks. Rejecting keeps the candidate with the reason.
Nothing is ever substituted automatically.
"""

import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from app.alternatives.graph import InvestigationInput, build_graph
from app.domain.enums import AlternativeStatus, DemoRole, FitClass
from app.domain.errors import ConflictError
from app.domain.ids import new_id
from app.domain.models import Alternative, AuditEvent, BomLine, Job, Override
from app.domain.mpn import normalize_mpn
from app.infra.repositories import Filter, Repositories
from app.ingestion.normalize import normalize_manufacturer
from app.ingestion.service import ensure_not_busy
from app.ingestion.validate import revalidate
from app.jobs.dispatcher import JobContext
from app.risk.service import InsightService
from app.sourcing.chain import OfferSourceChain
from app.sourcing.service import SELECTED_OFFER_OVERRIDE, SourcingService

logger = logging.getLogger(__name__)


@dataclass
class AlternativesService:
    repos: Repositories
    chain: OfferSourceChain
    sourcing: SourcingService
    insights: InsightService
    model: BaseChatModel | None = None

    async def investigate(self, project_id: str, line_id: str) -> list[Alternative]:
        project = await self.repos.projects.get(project_id)
        line = await self.repos.lines(project_id).get(line_id)
        component = (
            await self.repos.components(project_id).find(line.match.component_id)
            if line.match.component_id
            else None
        )
        selected = (
            await self.repos.offers(project_id).find(line.selected_offer_id)
            if line.selected_offer_id
            else None
        )

        run = build_graph(
            self.chain, InvestigationInput(project, line, component, selected), self.model
        )
        state = await run({})
        proposed: list[Alternative] = state.get("alternatives", [])

        repo = self.repos.alternatives(project_id)
        existing = {a.id: a for a in await self.for_line(project_id, line_id)}
        merged = [
            alt.model_copy(
                update={
                    "status": existing[alt.id].status,
                    "decided_by": existing[alt.id].decided_by,
                    "note": existing[alt.id].note,
                }
            )
            if alt.id in existing and existing[alt.id].status is not AlternativeStatus.PROPOSED
            else alt
            for alt in proposed
        ]
        await self.repos.evidence(project_id).put_many(state.get("evidence", {}).values())
        await repo.put_many(merged)
        logger.info(
            "Investigated alternates",
            extra={"fields": {"line": line_id, "candidates": len(merged)}},
        )
        return merged

    async def for_line(self, project_id: str, line_id: str) -> list[Alternative]:
        page = await self.repos.alternatives(project_id).list(
            filters=[Filter("line_id", "==", line_id)], limit=50
        )
        return page.items

    async def decide(
        self, project_id: str, alternative_id: str, approve: bool, note: str, role: DemoRole
    ) -> tuple[Alternative, BomLine]:
        project = await self.repos.projects.get(project_id)
        ensure_not_busy(project)
        alt = await self.repos.alternatives(project_id).get(alternative_id)
        line = await self.repos.lines(project_id).get(alt.line_id)
        _ensure_decidable(alt, approve)

        if not approve:
            rejected = alt.model_copy(
                update={"status": AlternativeStatus.REJECTED, "decided_by": role, "note": note}
            )
            await self.repos.alternatives(project_id).put(rejected)
            await self._audit(project_id, role, "ALTERNATE_REJECTED", alt, note)
            return rejected, line

        if alt.fit_class is FitClass.NOT_SUITABLE:
            raise ConflictError(
                "This candidate was assessed as not suitable and cannot be approved",
                {"fit_class": alt.fit_class.value},
            )
        for other in await self.for_line(project_id, line.id):
            if other.id != alt.id and other.status is AlternativeStatus.APPROVED:
                await self.repos.alternatives(project_id).put(
                    other.model_copy(update={"status": AlternativeStatus.PROPOSED})
                )

        overrides = {k: v for k, v in line.overrides.items() if k != SELECTED_OFFER_OVERRIDE}
        overrides["mpn"] = Override(old=line.mpn, new=alt.candidate_mpn, reason=note, by=role)
        substituted = line.model_copy(
            update={
                "mpn": normalize_mpn(alt.candidate_mpn),
                "manufacturer": normalize_manufacturer(alt.manufacturer),
                "substituted_from": line.substituted_from or line.mpn,
                "overrides": overrides,
                "version": line.version + 1,
            }
        )
        substituted = substituted.model_copy(update={"validation": revalidate(substituted)})
        await self.repos.lines(project_id).put(substituted)
        approved = alt.model_copy(
            update={"status": AlternativeStatus.APPROVED, "decided_by": role, "note": note}
        )
        await self.repos.alternatives(project_id).put(approved)
        await self.sourcing.source(project, [substituted])
        await self.insights.refresh(project_id)
        await self._audit(project_id, role, "ALTERNATE_APPROVED", alt, note)
        return approved, await self.repos.lines(project_id).get(line.id)

    async def _audit(
        self, project_id: str, role: DemoRole, action: str, alt: Alternative, note: str
    ) -> None:
        await self.repos.audit(project_id).put(
            AuditEvent(
                id=new_id("aud"),
                actor_role=role,
                action=action,
                target=f"line:{alt.line_id}",
                before={"alternative": alt.id, "candidate": alt.candidate_mpn},
                after={"fit_class": alt.fit_class.value},
                reason=note,
            )
        )


@dataclass
class AlternativesJob:
    """Job handler for JobType.ALTERNATIVES (payload: line_id)."""

    service: AlternativesService

    async def __call__(self, job: Job, ctx: JobContext) -> None:
        line_id = job.payload.get("line_id")
        if not isinstance(line_id, str):
            raise ConflictError("Alternatives job has no line_id")
        await ctx.progress("investigating", 30)
        found = await self.service.investigate(job.project_id, line_id)
        if not found:
            await ctx.warn("No known alternates for this part in the catalog")


def _ensure_decidable(alt: Alternative, approve: bool) -> None:
    """A decision is recorded once (a double click must not re-apply it or duplicate the
    audit entry). An approved alternate has already replaced the line, so it cannot simply be
    rejected; a rejected one may still be approved if the reviewer changes their mind."""
    if alt.status is AlternativeStatus.APPROVED:
        raise ConflictError(
            "This alternate is already approved and applied to the line. To undo it, approve a "
            "different alternate or edit the line.",
            {"status": alt.status.value},
        )
    if alt.status is AlternativeStatus.REJECTED and not approve:
        raise ConflictError("This alternate is already rejected", {"status": alt.status.value})
