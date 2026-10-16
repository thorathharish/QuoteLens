"""Sourcing use case: fetch offers for BOM lines, match, recommend, and persist with evidence.

Ids are deterministic (line + distributor + SKU), so re-running overwrites. A user's offer
override survives re-runs while that offer still exists.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.catalog.rows import CatalogComponent, CatalogOffer
from app.domain.enums import EvidenceKind, MatchStatus, SourceMode
from app.domain.facts import Evidence
from app.domain.models import BomLine, Component, Offer, PriceBreak, Project
from app.infra.repositories import Repositories
from app.sourcing.chain import OfferSourceChain
from app.sourcing.matcher import match_line
from app.sourcing.offer_selector import recommend_offer

logger = logging.getLogger(__name__)

SELECTED_OFFER_OVERRIDE = "selected_offer_id"


@dataclass
class SourcingOutcome:
    matched: int = 0
    not_found: int = 0
    warnings: list[str] = field(default_factory=list)


def _digest(*parts: str, size: int = 10) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:size]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:20]


def offer_id(line_id: str, distributor: str, sku: str) -> str:
    return f"off_{line_id}_{_slug(distributor)}_{_digest(distributor, sku, size=8)}"


def offer_evidence_id(distributor: str, sku: str) -> str:
    return f"ev_off_{_digest(distributor, sku)}"


def component_evidence_id(mpn: str) -> str:
    return f"ev_cmp_{_digest(mpn)}"


def primary_volume(project: Project) -> int:
    """Recommendations are scored at the first (primary) build quantity."""
    return project.build_quantities[0]


@dataclass
class SourcingService:
    repos: Repositories
    chain: OfferSourceChain

    async def source(self, project: Project, lines: list[BomLine]) -> SourcingOutcome:
        outcome = SourcingOutcome()
        sourceable = [line for line in lines if line.mpn and not line.dnp]
        result = await self.chain.fetch(
            [line.mpn for line in sourceable if line.mpn], project.data_mode
        )
        outcome.warnings.extend(result.errors)

        offers: list[Offer] = []
        evidence: dict[str, Evidence] = {}
        components: dict[str, Component] = {}
        updated: list[BomLine] = []
        volume = primary_volume(project)

        for line in lines:
            if line.dnp or line.mpn is None:
                updated.append(
                    line.model_copy(
                        update={
                            "match": match_line(line.mpn, line.manufacturer, {}, []),
                            "selected_offer_id": None,
                            "recommendation": None,
                        }
                    )
                )
                continue
            candidates = (
                [] if line.mpn in result.components else await self.chain.search.suggest(line.mpn)
            )
            match = match_line(line.mpn, line.manufacturer, result.components, candidates)
            line_offers: list[Offer] = []
            if match.status is MatchStatus.MATCHED:
                outcome.matched += 1
                catalog_offers = result.offers.get(line.mpn, [])
                component = result.components[line.mpn]
                components[component.mpn_norm] = component_from_catalog(
                    component, catalog_offers, evidence
                )
                line_offers = [offer_from_catalog(line.id, o, evidence) for o in catalog_offers]
            else:
                outcome.not_found += 1

            need = (line.qty_per.value or Decimal(0)) * volume
            recommendation = recommend_offer(
                line_offers, need, volume, project.currency, project.assumptions.fx_overrides
            )
            offer_ids = {o.id for o in line_offers}
            user_choice = (
                line.selected_offer_id if SELECTED_OFFER_OVERRIDE in line.overrides else None
            )
            selected = user_choice if user_choice in offer_ids else recommendation.offer_id
            offers.extend(line_offers)
            updated.append(
                line.model_copy(
                    update={
                        "match": match,
                        "recommendation": recommendation,
                        "selected_offer_id": selected,
                    }
                )
            )

        await self._persist(
            project.id, lines, updated, offers, list(evidence.values()), list(components.values())
        )
        logger.info(
            "Sourced lines",
            extra={
                "fields": {
                    "matched": outcome.matched,
                    "not_found": outcome.not_found,
                    "offers": len(offers),
                }
            },
        )
        return outcome

    async def _persist(
        self,
        project_id: str,
        original: list[BomLine],
        lines: list[BomLine],
        offers: list[Offer],
        evidence: list[Evidence],
        components: list[Component],
    ) -> None:
        offer_repo = self.repos.offers(project_id)
        touched = {line.id for line in original}
        keep = {o.id for o in offers}
        for stale in await offer_repo.all():
            if stale.line_id in touched and stale.id not in keep:
                await offer_repo.delete(stale.id)
        await self.repos.evidence(project_id).put_many(evidence)
        await self.repos.components(project_id).put_many(components)
        await offer_repo.put_many(offers)
        await self.repos.lines(project_id).put_many(lines)


def offer_from_catalog(line_id: str, row: CatalogOffer, evidence: dict[str, Evidence]) -> Offer:
    ev_id = offer_evidence_id(row.distributor, row.sku)
    label = {
        SourceMode.LIVE: "live",
        SourceMode.CACHE: "cached",
        SourceMode.DEMO_SNAPSHOT: "demo snapshot",
    }[row.mode]
    evidence[ev_id] = Evidence(
        id=ev_id,
        kind=EvidenceKind.DISTRIBUTOR_OFFER,
        source_name=f"{row.distributor} ({label})",
        source_ref=row.source_url or row.sku,
        fetched_at=row.fetched_at,
        mode=row.mode,
        payload_excerpt={
            "sku": row.sku,
            "stock": row.stock,
            "moq": row.moq,
            "multiple": row.mult,
            "lead_days": row.lead_days,
            "lifecycle": row.lifecycle.value,
            "authorized": row.authorized,
            "currency": row.currency,
            "price_breaks": [{"qty": b.qty, "price": str(b.price)} for b in row.price_breaks],
        },
    )
    return Offer(
        id=offer_id(line_id, row.distributor, row.sku),
        line_id=line_id,
        distributor=row.distributor,
        sku=row.sku,
        mpn=row.mpn_norm,
        manufacturer=row.manufacturer,
        authorized=row.authorized,
        stock=row.stock,
        moq=row.moq,
        order_multiple=row.mult,
        packaging=row.packaging,
        lead_time_days=row.lead_days,
        lifecycle=row.lifecycle,
        price_breaks=[PriceBreak(qty=b.qty, unit_price=b.price) for b in row.price_breaks],
        currency=row.currency,
        evidence_id=ev_id,
        mode=row.mode,
        fetched_at=row.fetched_at,
    )


def component_from_catalog(
    row: CatalogComponent, offers: list[CatalogOffer], evidence: dict[str, Evidence]
) -> Component:
    ev_id = component_evidence_id(row.mpn_norm)
    evidence[ev_id] = Evidence(
        id=ev_id,
        kind=EvidenceKind.CATALOG_SNAPSHOT,
        source_name=row.source,
        source_ref=row.mpn,
        mode=offers[0].mode if offers else SourceMode.CACHE,
        payload_excerpt={
            "lifecycle": row.lifecycle.value,
            "ltb_date": row.ltb_date.isoformat() if row.ltb_date else None,
            "category": row.category,
            "description": row.description,
            "snapshot_date": row.snapshot_date.isoformat(),
        },
    )
    return Component(
        id=row.mpn_norm,
        mpn=row.mpn,
        manufacturer=row.manufacturer,
        category=row.category,
        description=row.description,
        params=dict(row.params),
        lifecycle=row.lifecycle,
        ltb_date=row.ltb_date,
        datasheet_url=row.datasheet_url,
        evidence_id=ev_id,
    )
