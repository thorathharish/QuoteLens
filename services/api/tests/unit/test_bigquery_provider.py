"""BigQueryCatalogProvider without a real BigQuery: queries are captured and rows faked
in the shape the BigQuery client returns. The real round trip is tracked in issue #3."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from google.cloud import bigquery

from app.domain.enums import Lifecycle, SourceMode
from app.sourcing.providers.catalog import BigQueryCatalogProvider


def _provider(
    rows: dict[str, list[dict[str, Any]]], calls: list[tuple[str, list[Any]]]
) -> BigQueryCatalogProvider:
    provider = object.__new__(BigQueryCatalogProvider)
    provider._bq = bigquery
    provider._prefix = "`proj.catalog`"
    provider._keys = None

    def fake_query(sql: str, params: list[Any]) -> list[dict[str, Any]]:
        calls.append((sql, params))
        table = "offers_cache" if "offers_cache" in sql else "components"
        return rows[table]

    provider._query = fake_query  # type: ignore[method-assign]
    return provider


COMPONENT = {
    "mpn_norm": "A1101ELHLT-T",
    "mpn": "A1101ELHLT-T",
    "manufacturer": "Allegro MicroSystems",
    "category": "hall_sensor",
    "description": "Hall switch",
    "package": "SOT-23W",
    "params": '{"package": "SOT-23W"}',
    "lifecycle": "OBSOLETE",
    "ltb_date": date(2026, 3, 31),
    "rohs": True,
    "datasheet_url": None,
    "source": "demo",
    "snapshot_date": date(2026, 10, 17),
}
OFFER = {
    "mpn_norm": "A1101ELHLT-T",
    "distributor": "DigiKey",
    "sku": "DEMO-DK-A1101",
    "manufacturer": "Allegro",
    "stock": 0,
    "moq": 1,
    "mult": 1,
    "lead_days": None,
    "packaging": "Cut Tape",
    "price_breaks": [{"qty": 1, "price": Decimal("0.841")}],
    "currency": "USD",
    "authorized": True,
    "lifecycle": "OBSOLETE",
    "fetched_at": datetime(2026, 10, 17, 6, tzinfo=UTC),
    "mode": "DEMO_SNAPSHOT",
    "source_url": None,
}


async def test_fetch_binds_parameters_and_maps_rows() -> None:
    calls: list[tuple[str, list[Any]]] = []
    provider = _provider({"components": [COMPONENT], "offers_cache": [OFFER]}, calls)

    result = await provider.fetch(["A1101ELHLT-T", "A1101ELHLT-T"])

    component = result.components["A1101ELHLT-T"]
    assert component.lifecycle is Lifecycle.OBSOLETE
    assert component.params == {"package": "SOT-23W"}
    offer = result.offers["A1101ELHLT-T"][0]
    assert offer.mode is SourceMode.DEMO_SNAPSHOT
    assert offer.price_breaks[0].price == Decimal("0.841")

    for sql, params in calls:
        assert "A1101" not in sql  # values are never formatted into SQL
        assert "IN UNNEST(@mpns)" in sql
        mpns = next(p for p in params if p.name == "mpns")
        assert mpns.values == ["A1101ELHLT-T"]  # de-duplicated
    offers_sql = next(sql for sql, _ in calls if "offers_cache" in sql)
    assert "fetched_at >= @since" in offers_sql  # partition filter
    assert "QUALIFY ROW_NUMBER()" in offers_sql  # latest snapshot per SKU


async def test_suggest_caches_the_key_list() -> None:
    calls: list[tuple[str, list[Any]]] = []
    provider = _provider({"components": [{"mpn_norm": "TPS54331DDR"}], "offers_cache": []}, calls)
    assert await provider.suggest("TPS5431DDR") == ["TPS54331DDR"]
    assert await provider.suggest("TPS5431DDR") == ["TPS54331DDR"]
    assert len(calls) == 1
    assert await provider.fetch([]) is not None


@pytest.mark.parametrize("bad", ["proj; DROP TABLE x", "data`set"])
def test_rejects_unsafe_identifiers(bad: str) -> None:
    with pytest.raises(ValueError, match="Invalid BigQuery identifier"):
        BigQueryCatalogProvider(bad, "catalog", "us-central1")
