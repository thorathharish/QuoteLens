"""Provider chain honoring the project's data mode (ADR-0005).

- demo_snapshot: catalog only.
- cache_first:   catalog; live providers only for parts the catalog lacks.
- live_first:    live providers; catalog for parts they did not return.

A failing live provider never fails the analysis: its error is recorded and the chain
falls back to the catalog, so degraded data is visible instead of hidden.
"""

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.domain.enums import DataMode, SourceMode
from app.sourcing.providers.base import (
    CacheWriter,
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
        cache_writer: CacheWriter | None = None,
    ) -> None:
        self.catalog = catalog
        self.search = search
        self.crossrefs = crossrefs
        self.cache_writer = cache_writer
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
        result.merge(await self._from_live(_missing_or_stale(wanted, result)))
        return result

    async def _from_live(self, mpns: list[str]) -> ProviderResult:
        result = ProviderResult()
        if not mpns:
            return result
        for partial in await asyncio.gather(*(self._safe(p, mpns) for p in self.live)):
            result.merge(partial)
        await self._write_through(result)
        return result

    async def _write_through(self, result: ProviderResult) -> None:
        live = [o for offers in result.offers.values() for o in offers if o.mode is SourceMode.LIVE]
        if not live or self.cache_writer is None:
            return
        try:
            await self.cache_writer.write(live)
        except Exception:
            logger.warning("Writing live offers to the cache failed", exc_info=True)
            result.errors.append("Live prices were used but could not be cached")

    async def _safe(self, provider: OfferProvider, mpns: list[str]) -> ProviderResult:
        if not mpns:
            return ProviderResult()
        try:
            return await provider.fetch(mpns)
        except Exception as exc:
            logger.warning("Offer provider %s failed", provider.name, exc_info=True)
            return ProviderResult(errors=[f"{provider.name} unavailable ({type(exc).__name__})"])


STALE_AFTER = timedelta(days=7)


def _missing(mpns: list[str], result: ProviderResult) -> list[str]:
    return [m for m in mpns if not result.offers.get(m)]


def _missing_or_stale(mpns: list[str], result: ProviderResult) -> list[str]:
    """Parts without offers, or whose cached offers are all older than a week. Demo snapshot
    data never counts as stale: it is disclosed as a snapshot instead."""
    cutoff = datetime.now(UTC) - STALE_AFTER
    return [
        m
        for m in mpns
        if not result.offers.get(m)
        or all(o.mode is SourceMode.CACHE and o.fetched_at < cutoff for o in result.offers[m])
    ]
