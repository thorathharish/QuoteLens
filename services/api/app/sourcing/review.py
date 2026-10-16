"""User decisions on sourcing: correct an MPN / accept a suggested match, override the
recommended offer. Every change is audited and re-validated; nothing is applied silently."""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import DemoRole, EvidenceKind
from app.domain.errors import ValidationFailedError
from app.domain.facts import Evidence, actual
from app.domain.ids import new_id
from app.domain.models import AuditEvent, BomLine, Override
from app.domain.mpn import normalize_mpn
from app.infra.repositories import Filter, Repositories
from app.ingestion.normalize import normalize_manufacturer, normalize_uom
from app.ingestion.service import ensure_not_busy
from app.ingestion.validate import revalidate
from app.risk.service import InsightService
from app.sourcing.service import SELECTED_OFFER_OVERRIDE, SourcingService


@dataclass(frozen=True)
class LineChanges:
    mpn: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    qty_per: Decimal | None = None
    uom: str | None = None
    dnp: bool | None = None


_RESOURCE_FIELDS = {"mpn", "qty_per", "uom", "dnp"}


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

    async def edit_line(
        self, project_id: str, line_id: str, changes: LineChanges, reason: str, role: DemoRole
    ) -> BomLine:
        """Correct BOM data. User-entered values become ACTUAL facts citing a USER_OVERRIDE
        evidence record, so even manual edits keep their provenance."""
        project = await self.repos.projects.get(project_id)
        ensure_not_busy(project)
        line = await self.repos.lines(project_id).get(line_id)
        update: dict[str, object] = {}
        overrides = dict(line.overrides)
        evidence: list[Evidence] = []

        def record(field: str, old: object, new: object) -> None:
            overrides[field] = Override(
                old=None if old is None else str(old),
                new=None if new is None else str(new),
                reason=reason,
                by=role,
            )

        if changes.mpn is not None:
            mpn = normalize_mpn(changes.mpn)
            if mpn is None:
                raise ValidationFailedError("MPN must not be empty")
            if mpn != line.mpn:
                record("mpn", line.mpn, mpn)
                update["mpn"] = mpn
        if changes.manufacturer is not None:
            maker = normalize_manufacturer(changes.manufacturer)
            if maker != line.manufacturer:
                record("manufacturer", line.manufacturer, maker)
                update["manufacturer"] = maker
        if changes.description is not None and changes.description != line.description:
            record("description", line.description, changes.description)
            update["description"] = changes.description
        if changes.uom is not None and normalize_uom(changes.uom) != line.uom:
            record("uom", line.uom, normalize_uom(changes.uom))
            update["uom"] = normalize_uom(changes.uom)
        if changes.dnp is not None and changes.dnp != line.dnp:
            record("dnp", line.dnp, changes.dnp)
            update["dnp"] = changes.dnp
        if changes.qty_per is not None and changes.qty_per != line.qty_per.value:
            ev = Evidence(
                id=f"ev_usr_{line.id}_v{line.version + 1}",
                kind=EvidenceKind.USER_OVERRIDE,
                source_name=f"Edited by {role.value}",
                source_ref=f"line {line.line_no}",
                payload_excerpt={
                    "field": "qty_per",
                    "old": str(line.qty_per.value),
                    "new": str(changes.qty_per),
                    "reason": reason,
                },
            )
            evidence.append(ev)
            record("qty_per", line.qty_per.value, changes.qty_per)
            update["qty_per"] = actual(changes.qty_per, ev.id)
        if not update:
            raise ValidationFailedError("No changes: every value equals the current one")

        update["overrides"] = overrides
        update["version"] = line.version + 1
        edited = line.model_copy(update=update)
        edited = edited.model_copy(update={"validation": revalidate(edited)})
        await self.repos.evidence(project_id).put_many(evidence)
        await self.repos.lines(project_id).put(edited)
        if _RESOURCE_FIELDS & set(update):
            await self.sourcing.source(project, [edited])
        await self.insights.refresh(project_id)
        changed = [k for k in update if k not in ("overrides", "version")]
        await self._audit(
            project_id,
            role,
            "LINE_EDITED",
            line_id,
            {k: _plain(line, k) for k in changed},
            {k: _plain(edited, k) for k in changed},
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


def _plain(line: BomLine, field: str) -> object:
    """Audit-friendly value of a line field (facts reduced to their value)."""
    return line.qty_per.value if field == "qty_per" else getattr(line, field)


def _json(value: object) -> str | None:
    return None if value is None else str(value)
