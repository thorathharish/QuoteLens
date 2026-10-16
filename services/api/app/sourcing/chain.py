"""Provider chain honoring the project's data mode (ADR-0005).

- demo_snapshot: catalog only.
- cache_first:   catalog; live providers only for parts the catalog lacks.
- live_first:    live providers; catalog for parts they did not return.

A failing live provider never fails the analysis: its error is recorded and the chain
falls back to the catalog, so degraded data is visible instead of hidden.
"""

import logging
from collections.abc import Sequence

from app.domain.enums import DataMode
from app.sourcing.providers.base import (
    CatalogSearch,
    CrossRefSource,
    OfferProvider,
    ProviderResult,
)

logger = logging.getLogger(__name__)


class OfferSourceChain:
    def __init__(
        self,
        catalog: OfferProvider,
        search: CatalogSearch,
        live: Sequence[OfferProvider] = (),
        crossrefs: CrossRefSource | None = None,
    ) -> None:
        self.catalog = catalog
        self.search = search
        self.crossrefs = crossrefs
        self.live = list(live)

    async def fetch(self, mpns: Sequence[str], mode: DataMode) -> ProviderResult:
        wanted = list(dict.fromkeys(mpns))
        if mode is DataMode.DEMO_SNAPSHOT or not self.live:
            return await self._safe(self.catalog, wanted)

        if mode is DataMode.LIVE_FIRST:
            result = await self._from_live(wanted)
            result.merge(await self._safe(self.catalog, _missing(wanted, result)))
            return result

        result = await self._safe(self.catalog, wanted)
        result.merge(await self._from_live(_missing(wanted, result)))
        return result

    async def _from_live(self, mpns: list[str]) -> ProviderResult:
        result = ProviderResult()
        for provider in self.live:
            if not mpns:
                break
            result.merge(await self._safe(provider, mpns))
        return result

    async def _safe(self, provider: OfferProvider, mpns: list[str]) -> ProviderResult:
        if not mpns:
            return ProviderResult()
        try:
            return await provider.fetch(mpns)
        except Exception as exc:
            logger.warning("Offer provider %s failed", provider.name, exc_info=True)
            return ProviderResult(errors=[f"{provider.name} unavailable ({type(exc).__name__})"])


def _missing(mpns: list[str], result: ProviderResult) -> list[str]:
    return [m for m in mpns if not result.offers.get(m)]
