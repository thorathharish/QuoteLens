"""Offer provider interface. Providers are batched (one call per BOM, not per part) and
return provider-neutral catalog rows, so live distributor adapters and the BigQuery cache
are interchangeable."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.catalog.rows import CatalogComponent, CatalogOffer


@dataclass
class ProviderResult:
    components: dict[str, CatalogComponent] = field(default_factory=dict)
    offers: dict[str, list[CatalogOffer]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def merge(self, other: "ProviderResult") -> None:
        for mpn, component in other.components.items():
            self.components.setdefault(mpn, component)
        for mpn, offers in other.offers.items():
            self.offers.setdefault(mpn, []).extend(offers)
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
