"""Catalog providers: the seed files in memory (local/tests) and BigQuery (deployed)."""

import asyncio
import re
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from app.catalog.rows import CatalogComponent, CatalogCrossRef, CatalogOffer
from app.sourcing.providers.base import ProviderResult

SUGGEST_MIN_SCORE = 85
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


def _suggest(mpn: str, known: Sequence[str], limit: int) -> list[str]:
    """Near matches by edit similarity, plus parts that extend the given prefix
    (e.g. a BOM missing a packaging suffix). Never includes the input itself."""
    scored = process.extract(
        mpn, known, scorer=fuzz.ratio, limit=limit * 3, score_cutoff=SUGGEST_MIN_SCORE
    )
    candidates = [match for match, _, _ in scored]
    if len(mpn) >= 6:
        candidates += [k for k in known if k.startswith(mpn) and k != mpn]
    unique = list(dict.fromkeys(c for c in candidates if c != mpn))
    return unique[:limit]


class SeedCatalogProvider:
    """Reads data/catalog_seed/*.jsonl once. Same data the BigQuery tables are loaded from."""

    name = "catalog"

    def __init__(self, seed_dir: Path) -> None:
        self.components = {
            c.mpn_norm: c for c in _read(seed_dir / "components.jsonl", CatalogComponent)
        }
        self._offers: dict[str, list[CatalogOffer]] = defaultdict(list)
        for offer in _read(seed_dir / "offers.jsonl", CatalogOffer):
            self._offers[offer.mpn_norm].append(offer)
        self.crossrefs = _read(seed_dir / "crossrefs.jsonl", CatalogCrossRef)

    async def fetch(self, mpns: Sequence[str]) -> ProviderResult:
        wanted = set(mpns)
        return ProviderResult(
            components={m: c for m, c in self.components.items() if m in wanted},
            offers={m: list(self._offers[m]) for m in wanted if m in self._offers},
        )

    async def suggest(self, mpn: str, limit: int = 3) -> list[str]:
        return _suggest(mpn, list(self.components), limit)


def _read[M: (CatalogComponent, CatalogOffer, CatalogCrossRef)](
    path: Path, model: type[M]
) -> list[M]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [model.model_validate_json(line) for line in lines if line.strip()]


class BigQueryCatalogProvider:
    """One parameterized query per table per BOM (`IN UNNEST(@mpns)`), partition-filtered.

    Table identifiers come from configuration (validated); values are always bound
    parameters, never formatted into SQL.
    """

    name = "catalog"
    LOOKBACK_DAYS = 400  # snapshot rows may be old; the UI shows their age
    KEYS_TTL_SECONDS = 600

    def __init__(self, project: str, dataset: str, location: str) -> None:
        for identifier in (project, dataset):
            if not _IDENTIFIER.match(identifier):
                raise ValueError(f"Invalid BigQuery identifier: {identifier!r}")
        from google.cloud import bigquery

        self._bq = bigquery
        self._client = bigquery.Client(project=project, location=location)
        self._prefix = f"`{project}.{dataset}`"
        self._keys: tuple[float, list[str]] | None = None

    def _query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        config = self._bq.QueryJobConfig(query_parameters=params)
        return [dict(row.items()) for row in self._client.query(sql, job_config=config).result()]

    async def fetch(self, mpns: Sequence[str]) -> ProviderResult:
        if not mpns:
            return ProviderResult()
        mpn_param = self._bq.ArrayQueryParameter("mpns", "STRING", sorted(set(mpns)))
        since = datetime.now(UTC) - timedelta(days=self.LOOKBACK_DAYS)
        # Table identifiers can't be bound as parameters; they come from validated config
        # (_IDENTIFIER). Every value is a bound query parameter.
        components_sql = (
            "SELECT mpn_norm, mpn, manufacturer, category, description, package, "  # noqa: S608
            "TO_JSON_STRING(params) AS params, lifecycle, ltb_date, rohs, datasheet_url, source, "
            f"snapshot_date FROM {self._prefix}.components WHERE mpn_norm IN UNNEST(@mpns)"
        )
        offers_sql = (
            "SELECT mpn_norm, distributor, sku, manufacturer, stock, moq, mult, lead_days, "  # noqa: S608
            "packaging, price_breaks, currency, authorized, lifecycle, fetched_at, mode, "
            "source_url "
            f"FROM {self._prefix}.offers_cache "
            "WHERE mpn_norm IN UNNEST(@mpns) AND fetched_at >= @since "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY mpn_norm, distributor, sku "
            "ORDER BY fetched_at DESC) = 1"
        )
        since_param = self._bq.ScalarQueryParameter("since", "TIMESTAMP", since)
        component_rows, offer_rows = await asyncio.gather(
            asyncio.to_thread(self._query, components_sql, [mpn_param]),
            asyncio.to_thread(self._query, offers_sql, [mpn_param, since_param]),
        )
        result = ProviderResult()
        for row in component_rows:
            component = CatalogComponent.model_validate(_component_row(row))
            result.components[component.mpn_norm] = component
        for row in offer_rows:
            offer = CatalogOffer.model_validate(row)
            result.offers.setdefault(offer.mpn_norm, []).append(offer)
        return result

    async def suggest(self, mpn: str, limit: int = 3) -> list[str]:
        now = time.monotonic()
        if self._keys is None or now - self._keys[0] > self.KEYS_TTL_SECONDS:
            rows = await asyncio.to_thread(
                self._query,
                f"SELECT mpn_norm FROM {self._prefix}.components",  # noqa: S608 (validated id)
                [],
            )
            self._keys = (now, [row["mpn_norm"] for row in rows])
        return _suggest(mpn, self._keys[1], limit)


def _component_row(row: dict[str, Any]) -> dict[str, Any]:
    import json

    params = row.get("params")
    return {**row, "params": json.loads(params) if isinstance(params, str) else (params or {})}
