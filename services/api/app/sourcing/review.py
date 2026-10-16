"""User decisions on sourcing: correct an MPN / accept a suggested match, override the
recommended offer. Every change is audited and re-validated; nothing is applied silently."""

from dataclasses import dataclass

from app.domain.enums import DemoRole
from app.domain.errors import ValidationFailedError
from app.domain.ids import new_id
from app.domain.models import AuditEvent, BomLine, Override
from app.domain.mpn import normalize_mpn
from app.infra.repositories import Filter, Repositories
from app.ingestion.normalize import normalize_manufacturer
from app.ingestion.service import ensure_not_busy
from app.ingestion.validate import revalidate
from app.risk.service import InsightService
from app.sourcing.service import SELECTED_OFFER_OVERRIDE, SourcingService


@dataclass
class SourcingReview:
    repos: Repositories
    sourcing: SourcingService
    insights: InsightService

    async def set_mpn(
        self,
        project_id: str,
        line_id: str,
        mpn: str,
        manufacturer: str | None,
        reason: str,
        role: DemoRole,
    ) -> BomLine:
        project = await self.repos.projects.get(project_id)
        ensure_not_busy(project)
        line = await self.repos.lines(project_id).get(line_id)
        new_mpn = normalize_mpn(mpn)
        if new_mpn is None:
            raise ValidationFailedError("MPN must not be empty")

        overrides = dict(line.overrides)
        overrides["mpn"] = Override(old=line.mpn, new=new_mpn, reason=reason, by=role)
        update: dict[str, object] = {"mpn": new_mpn, "overrides": overrides}
        if manufacturer:
            overrides["manufacturer"] = Override(
                old=line.manufacturer, new=manufacturer, reason=reason, by=role
            )
            update["manufacturer"] = normalize_manufacturer(manufacturer)
        edited = line.model_copy(update=update)
        edited = edited.model_copy(
            update={"validation": revalidate(edited), "version": line.version + 1}
        )
        await self.repos.lines(project_id).put(edited)
        await self.sourcing.source(project, [edited])
        await self.insights.refresh(project_id)
        await self._audit(
            project_id,
            role,
            "LINE_MPN_SET",
            line_id,
            {"mpn": line.mpn, "manufacturer": line.manufacturer},
            {"mpn": new_mpn, "manufacturer": edited.manufacturer},
            reason,
        )
        return await self.repos.lines(project_id).get(line_id)

    async def select_offer(
        self, project_id: str, line_id: str, offer_id: str, reason: str, role: DemoRole
    ) -> BomLine:
        project = await self.repos.projects.get(project_id)
        ensure_not_busy(project)
        line = await self.repos.lines(project_id).get(line_id)
        offers = await self.repos.offers(project_id).list(
            filters=[Filter("line_id", "==", line_id)], limit=200
        )
        if offer_id not in {o.id for o in offers.items}:
            raise ValidationFailedError(
                "That offer does not belong to this line", {"offer_id": offer_id}
            )

        overrides = dict(line.overrides)
        recommended = line.recommendation.offer_id if line.recommendation else None
        if offer_id == recommended:
            overrides.pop(SELECTED_OFFER_OVERRIDE, None)  # back to the recommendation
        else:
            overrides[SELECTED_OFFER_OVERRIDE] = Override(
                old=line.selected_offer_id, new=offer_id, reason=reason, by=role
            )
        updated = line.model_copy(update={"selected_offer_id": offer_id, "overrides": overrides})
        await self.repos.lines(project_id).put(updated)
        await self.insights.refresh(project_id)
        await self._audit(
            project_id,
            role,
            "OFFER_SELECTED",
            line_id,
            {"selected_offer_id": line.selected_offer_id},
            {"selected_offer_id": offer_id},
            reason,
        )
        return updated

    async def _audit(
        self,
        project_id: str,
        role: DemoRole,
        action: str,
        line_id: str,
        before: dict[str, object],
        after: dict[str, object],
        reason: str,
    ) -> None:
        await self.repos.audit(project_id).put(
            AuditEvent(
                id=new_id("aud"),
                actor_role=role,
                action=action,
                target=f"line:{line_id}",
                before={k: _json(v) for k, v in before.items()},
                after={k: _json(v) for k, v in after.items()},
                reason=reason,
            )
        )


def _json(value: object) -> str | None:
    return None if value is None else str(value)
