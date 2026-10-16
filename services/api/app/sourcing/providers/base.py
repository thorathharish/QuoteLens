"""Offer provider interface. Providers are batched (one call per BOM, not per part) and
return provider-neutral catalog rows, so live distributor adapters and the BigQuery cache
are interchangeable."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.catalog.rows import CatalogComponent, CatalogCrossRef, CatalogOffer


@dataclass
class ProviderResult:
    components: dict[str, CatalogComponent] = field(default_factory=dict)
    offers: dict[str, list[CatalogOffer]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "ProviderResult") -> None:
        """Combine results; for the same distributor SKU the most recently fetched offer wins."""
        for mpn, component in other.components.items():
            self.components.setdefault(mpn, component)
        for mpn, offers in other.offers.items():
            by_sku = {(o.distributor, o.sku): o for o in self.offers.get(mpn, [])}
            for offer in offers:
                current = by_sku.get((offer.distributor, offer.sku))
                if current is None or offer.fetched_at >= current.fetched_at:
                    by_sku[(offer.distributor, offer.sku)] = offer
            self.offers[mpn] = list(by_sku.values())
        self.errors.extend(other.errors)


class OfferProvider(Protocol):
    name: str

    async def fetch(self, mpns: Sequence[str]) -> ProviderResult:
        """Components and offers for normalized MPNs. Missing parts are simply absent."""
        ...


class CatalogSearch(Protocol):
    async def suggest(self, mpn: str, limit: int = 3) -> list[str]:
        """Known MPNs that closely resemble `mpn` (typos, missing suffixes)."""
        ...


class CacheWriter(Protocol):
    async def write(self, offers: list[CatalogOffer]) -> None:
        """Persist live offers so later analyses can use them as cached data."""
        ...


class CrossRefSource(Protocol):
    async def alternates(self, mpn: str) -> list[CatalogCrossRef]:
        """Curated alternates known for a part (form-fit-function or functional)."""
        ...
