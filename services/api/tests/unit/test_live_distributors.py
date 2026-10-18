"""Live distributor adapters, HTTP resilience and the provider chain, without network.

Response bodies mirror the real API shapes observed on 2026-10-17 (trimmed)."""

import asyncio
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from app.catalog.rows import CatalogOffer, CatalogPriceBreak
from app.config import Settings
from app.domain.enums import DataMode, Lifecycle, SourceMode
from app.infra.http import CircuitBreaker, CircuitOpenError, request
from app.sourcing.chain import OfferSourceChain
from app.sourcing.providers.base import ProviderResult
from app.sourcing.providers.live import (
    DigiKeyProvider,
    Element14Provider,
    MouserProvider,
    build_live_providers,
)

DIGIKEY_BODY = {
    "SearchLocaleUsed": {"Site": "US", "Language": "en", "Currency": "USD"},
    "Product": {
        "Description": {"ProductDescription": "IC OP AMP 1CH 8-TSSOP"},
        "Manufacturer": {"Id": 296, "Name": "Texas Instruments"},
        "ManufacturerProductNumber": "INA240A1PWR",
        "ProductUrl": "https://www.digikey.com/en/products/detail/texas-instruments/INA240A1PWR",
        "ProductVariations": [
            {
                "DigiKeyProductNumber": "296-45088-2-ND",
                "PackageType": {"Name": "Tape & Reel (TR)"},
                "StandardPricing": [{"BreakQuantity": 2000, "UnitPrice": 1.78885}],
                "MarketPlace": False,
                "QuantityAvailableforPackageType": 0,
                "MinimumOrderQuantity": 2000,
                "StandardPackage": 2000,
            },
            {
                "DigiKeyProductNumber": "296-45088-1-ND",
                "PackageType": {"Name": "Cut Tape (CT)"},
                "StandardPricing": [
                    {"BreakQuantity": 1, "UnitPrice": 3.33},
                    {"BreakQuantity": 10, "UnitPrice": 2.499},
                ],
                "MarketPlace": False,
                "QuantityAvailableforPackageType": 0,
                "MinimumOrderQuantity": 1,
                "StandardPackage": 1,
            },
            {
                "DigiKeyProductNumber": "296-45088-6-ND",
                "PackageType": {"Name": "Digi-Reel®"},
                "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 3.33}],
                "MarketPlace": False,
                "QuantityAvailableforPackageType": 0,
                "MinimumOrderQuantity": 1,
                "StandardPackage": 1,
            },
        ],
        "ProductStatus": {"Id": 0, "Status": "Active"},
        "EndOfLife": False,
        "ManufacturerLeadWeeks": "20",
        "Category": {"Name": "Integrated Circuits (ICs)"},
        "Parameters": [{"ParameterText": "Amplifier Type", "ValueText": "Current Sense"}],
    },
}

MOUSER_BODY = {
    "Errors": [],
    "SearchResults": {
        "NumberOfResult": 2,
        "Parts": [
            {
                "ManufacturerPartNumber": "INA240A1PWR",
                "Manufacturer": "Texas Instruments",
                "MouserPartNumber": "595-INA240A1PWR",
                "Description": "Current Sense Amplifiers",
                "Category": "Current Sense Amplifiers",
                "LeadTime": "140 Days",
                "LifecycleStatus": None,
                "Min": "1",
                "Mult": "1",
                "AvailabilityInStock": "8131",
                "ProductAttributes": [
                    {"AttributeName": "Packaging", "AttributeValue": "Reel"},
                    {"AttributeName": "Packaging", "AttributeValue": "Cut Tape"},
                ],
                "PriceBreaks": [
                    {"Quantity": 1, "Price": "₹318.15", "Currency": "INR"},
                    {"Quantity": 10, "Price": "₹238.85", "Currency": "INR"},
                ],
                "ProductDetailUrl": "https://www.mouser.in/ProductDetail/595-INA240A1PWR",
            },
            {
                "ManufacturerPartNumber": "INA240A1PW",
                "Manufacturer": "Texas Instruments",
                "MouserPartNumber": "595-INA240A1PW",
                "Min": "1",
                "Mult": "1",
                "PriceBreaks": [{"Quantity": 1, "Price": "₹330.00", "Currency": "INR"}],
            },
        ],
    },
}

E14_BODY = {
    "manufacturerPartNumberSearchReturn": {
        "numberOfResults": 1,
        "products": [
            {
                "sku": "9238603",
                "translatedManufacturerPartNumber": "RC0603FR-0710KL",
                "brandName": "YAGEO",
                "displayName": "YAGEO - RC0603FR-0710KL - SMD Chip Resistor",
                "productStatus": "STOCKED",
                "packSize": 1,
                "unitOfMeasure": "EACH (SUPPLIED ON CUT TAPE)",
                "translatedMinimumOrderQuality": 10,
                "stock": {"level": 1437578, "leastLeadTime": 195},
                "prices": [
                    {"from": 10, "to": 99, "cost": 1.45},
                    {"from": 100, "to": 499, "cost": 0.822},
                ],
            },
        ],
    }
}


# ── adapters ─────────────────────────────────────────────────


@respx.mock
async def test_digikey_maps_variations_and_marks_missing_inventory_unknown() -> None:
    respx.post("https://api.digikey.com/v1/oauth2/token").respond(
        200, json={"access_token": "t", "expires_in": 600}
    )
    respx.get(url__regex=r".*/products/v4/search/INA240A1PWR/productdetails").respond(
        200, json=DIGIKEY_BODY
    )
    result = await DigiKeyProvider("id", "secret").fetch(["INA240A1PWR"])

    offers = {o.sku: o for o in result.offers["INA240A1PWR"]}
    assert set(offers) == {"296-45088-2-ND", "296-45088-1-ND"}  # Digi-Reel (fee) excluded
    reel, cut = offers["296-45088-2-ND"], offers["296-45088-1-ND"]
    assert (reel.moq, reel.mult) == (2000, 2000)
    assert (cut.moq, cut.mult) == (1, 1)
    assert cut.stock is None  # no QuantityAvailable in the response → unknown, not zero
    assert cut.lead_days == 140
    assert cut.price_breaks[0].price == Decimal("3.33")
    assert cut.mode is SourceMode.LIVE
    assert cut.source_url is not None
    assert result.components["INA240A1PWR"].lifecycle is Lifecycle.ACTIVE


@respx.mock
async def test_digikey_reports_stock_when_present_and_encodes_part_numbers() -> None:
    body = {
        **DIGIKEY_BODY,
        "Product": {
            **DIGIKEY_BODY["Product"],
            "QuantityAvailable": 500,
            "ManufacturerProductNumber": "MCP2561-E/SN",
            "ProductVariations": [
                {
                    **DIGIKEY_BODY["Product"]["ProductVariations"][1],
                    "QuantityAvailableforPackageType": 500,
                }
            ],
        },
    }
    respx.post("https://api.digikey.com/v1/oauth2/token").respond(
        200, json={"access_token": "t", "expires_in": 600}
    )
    route = respx.get(url__regex=r".*/search/MCP2561-E%2FSN/productdetails").respond(200, json=body)
    result = await DigiKeyProvider("id", "secret").fetch(["MCP2561-E/SN"])
    assert route.called  # "/" is percent-encoded into the path
    assert result.offers["MCP2561-E/SN"][0].stock == 500


@respx.mock
async def test_digikey_not_found_and_token_refresh_on_401() -> None:
    token = respx.post("https://api.digikey.com/v1/oauth2/token").respond(
        200, json={"access_token": "t", "expires_in": 600}
    )
    respx.get(url__regex=r".*/TYPO123/productdetails").mock(
        side_effect=[httpx.Response(401), httpx.Response(404, json={"title": "Not Found"})]
    )
    keyword = respx.post("https://api.digikey.com/products/v4/search/keyword").respond(
        200, json={"Products": [{"ManufacturerProductNumber": "TYPO1234"}]}
    )
    result = await DigiKeyProvider("id", "secret").fetch(["TYPO123"])
    assert result.offers == {}  # the keyword hit is not an exact match
    assert result.errors == []
    assert token.call_count == 2  # refreshed after the 401
    assert keyword.called


@respx.mock
async def test_digikey_falls_back_to_keyword_search_when_several_products_share_the_mpn() -> None:
    respx.post("https://api.digikey.com/v1/oauth2/token").respond(
        200, json={"access_token": "t", "expires_in": 600}
    )
    respx.get(url__regex=r".*/INA240A1PWR/productdetails").respond(404)
    product = DIGIKEY_BODY["Product"]
    other_maker = {**product, "Manufacturer": {"Name": "Second Source Inc"}}
    near_miss = {**product, "ManufacturerProductNumber": "INA240A1PWRG4"}
    respx.post("https://api.digikey.com/products/v4/search/keyword").respond(
        200,
        json={
            "SearchLocaleUsed": {"Currency": "USD"},
            "Products": [near_miss, product, other_maker, product],
        },
    )
    result = await DigiKeyProvider("id", "secret").fetch(["INA240A1PWR"])
    offers = result.offers["INA240A1PWR"]
    assert {o.manufacturer for o in offers} == {"Texas Instruments"}
    assert len({o.sku for o in offers}) == len(offers)  # the repeated listing is not doubled
    assert result.components["INA240A1PWR"].manufacturer == "Texas Instruments"


@respx.mock
async def test_mouser_searches_ten_part_numbers_per_call() -> None:
    route = respx.post("https://api.mouser.com/api/v1/search/partnumber").respond(
        200, json=MOUSER_BODY
    )
    mpns = ["INA240A1PWR", *[f"P{i}" for i in range(11)]]
    result = await MouserProvider("key").fetch(mpns)
    assert route.call_count == 2
    sent = route.calls[0].request.content.decode()
    assert "INA240A1PWR|P0|P1" in sent
    assert list(result.offers) == ["INA240A1PWR"]


async def test_pacer_spaces_calls_to_the_rate_limit() -> None:
    from app.sourcing.providers.live import _Pacer

    pacer = _Pacer(20.0)
    start = time.monotonic()
    await asyncio.gather(*(pacer.wait() for _ in range(5)))
    assert time.monotonic() - start >= 0.19  # 4 gaps of 50 ms


@respx.mock
async def test_mouser_keeps_exact_matches_and_native_currency() -> None:
    respx.post("https://api.mouser.com/api/v1/search/partnumber").respond(200, json=MOUSER_BODY)
    result = await MouserProvider("key").fetch(["INA240A1PWR"])
    (offer,) = result.offers["INA240A1PWR"]  # the INA240A1PW non-exact hit is dropped
    assert offer.currency == "INR"
    assert offer.price_breaks[0].price == Decimal("318.15")
    assert offer.stock == 8131
    assert offer.lead_days == 140
    assert offer.packaging == "Reel, Cut Tape"


@respx.mock
async def test_mouser_api_errors_are_reported_not_raised() -> None:
    respx.post("https://api.mouser.com/api/v1/search/partnumber").respond(
        200, json={"Errors": [{"Message": "Invalid unique identifier."}], "SearchResults": None}
    )
    result = await MouserProvider("bad-key").fetch(["X1"])
    assert result.offers == {}
    assert result.errors == ["Mouser lookup failed (RuntimeError)"]


@respx.mock
async def test_element14_uses_store_currency_and_leaves_lead_time_unknown() -> None:
    respx.get("https://api.element14.com/catalog/products").respond(200, json=E14_BODY)
    result = await Element14Provider("key", "in.element14.com").fetch(["RC0603FR-0710KL"])
    (offer,) = result.offers["RC0603FR-0710KL"]
    assert offer.currency == "INR"
    assert offer.moq == 10
    assert offer.lead_days is None
    assert offer.stock == 1437578
    unknown_store = await Element14Provider("key", "xx.element14.com").fetch(["RC0603FR-0710KL"])
    assert unknown_store.offers == {}  # prices without a known currency are not interpreted


def test_providers_are_built_only_from_configured_keys() -> None:
    from pydantic import SecretStr

    settings = Settings(
        _env_file=None,
        mouser_api_key=SecretStr("k"),  # type: ignore[call-arg]
        digikey_client_id=SecretStr("id"),
        digikey_client_secret=SecretStr(" "),
    )
    assert [p.name for p in build_live_providers(settings)] == ["Mouser"]


# ── HTTP resilience ──────────────────────────────────────────


async def _no_sleep(_: float) -> None:
    return None


@respx.mock
async def test_retries_then_succeeds_and_opens_circuit_after_failures() -> None:
    route = respx.get("https://x.test/a").mock(
        side_effect=[httpx.Response(503), httpx.Response(200)]
    )
    breaker = CircuitBreaker("X", threshold=2, reset_seconds=60)
    async with httpx.AsyncClient() as client:
        assert (
            await request(client, breaker, "GET", "https://x.test/a", sleep=_no_sleep)
        ).status_code == 200
        assert route.call_count == 2

        respx.get("https://x.test/b").respond(500)
        for _ in range(2):
            with pytest.raises(httpx.HTTPStatusError):
                await request(client, breaker, "GET", "https://x.test/b", sleep=_no_sleep)
        with pytest.raises(CircuitOpenError):
            await request(client, breaker, "GET", "https://x.test/b", sleep=_no_sleep)

        not_found = respx.get("https://x.test/c").respond(404)
        breaker.opened_at = None
        assert (
            await request(client, breaker, "GET", "https://x.test/c", sleep=_no_sleep)
        ).status_code == 404
        assert not_found.call_count == 1  # 4xx is an answer, not a failure to retry


# ── chain: stale refresh, newest wins, write-through ─────────


def _offer(mode: SourceMode, age_days: int, price: str = "1.00") -> CatalogOffer:
    return CatalogOffer(
        mpn_norm="P1",
        distributor="DigiKey",
        sku="S1",
        manufacturer="M",
        moq=1,
        mult=1,
        price_breaks=[CatalogPriceBreak(qty=1, price=Decimal(price))],
        currency="USD",
        fetched_at=datetime.now(UTC) - timedelta(days=age_days),
        mode=mode,
    )


class StaticProvider:
    def __init__(self, name: str, offers: list[CatalogOffer], fail: bool = False) -> None:
        self.name, self.offers, self.fail, self.calls = name, offers, fail, 0

    async def fetch(self, mpns: Sequence[str]) -> ProviderResult:
        self.calls += 1
        if self.fail:
            raise TimeoutError
        return ProviderResult(offers={"P1": list(self.offers)} if self.offers else {})

    async def suggest(self, mpn: str, limit: int = 3) -> list[str]:
        return []


class RecordingWriter:
    def __init__(self, fail: bool = False) -> None:
        self.written: list[CatalogOffer] = []
        self.fail = fail

    async def write(self, offers: list[CatalogOffer]) -> None:
        if self.fail:
            raise RuntimeError("bigquery down")
        self.written.extend(offers)


async def test_stale_cache_is_refreshed_and_live_offer_replaces_it() -> None:
    cache = StaticProvider("catalog", [_offer(SourceMode.CACHE, 30, "2.00")])
    live = StaticProvider("DigiKey", [_offer(SourceMode.LIVE, 0, "1.50")])
    writer = RecordingWriter()
    chain = OfferSourceChain(cache, cache, [live], cache_writer=writer)
    result = await chain.fetch(["P1"], DataMode.CACHE_FIRST)
    (offer,) = result.offers["P1"]  # same distributor SKU: newest wins
    assert offer.mode is SourceMode.LIVE
    assert offer.price_breaks[0].price == Decimal("1.50")
    assert [o.sku for o in writer.written] == ["S1"]


async def test_fresh_cache_and_snapshots_skip_live_calls() -> None:
    live = StaticProvider("DigiKey", [_offer(SourceMode.LIVE, 0)])
    fresh = StaticProvider("catalog", [_offer(SourceMode.CACHE, 2)])
    await OfferSourceChain(fresh, fresh, [live]).fetch(["P1"], DataMode.CACHE_FIRST)
    old_snapshot = StaticProvider("catalog", [_offer(SourceMode.DEMO_SNAPSHOT, 400)])
    await OfferSourceChain(old_snapshot, old_snapshot, [live]).fetch(["P1"], DataMode.CACHE_FIRST)
    assert live.calls == 0


async def test_cache_write_failure_is_reported_not_fatal() -> None:
    cache = StaticProvider("catalog", [])
    live = StaticProvider("DigiKey", [_offer(SourceMode.LIVE, 0)])
    result = await OfferSourceChain(
        cache, cache, [live], cache_writer=RecordingWriter(fail=True)
    ).fetch(["P1"], DataMode.CACHE_FIRST)
    assert result.offers["P1"]
    assert result.errors == ["Live prices were used but could not be cached"]


@respx.mock
async def test_failed_lookups_never_log_the_api_key(caplog: pytest.LogCaptureFixture) -> None:
    from app.logging import JsonFormatter

    respx.post("https://api.mouser.com/api/v1/search/partnumber").respond(403)
    respx.get("https://api.element14.com/catalog/products").respond(403)
    with caplog.at_level(logging.DEBUG):
        await MouserProvider("sekret-mouser").fetch(["X1"])
        await Element14Provider("sekret-e14", "in.element14.com").fetch(["X1"])
    formatter = JsonFormatter()
    lines = [formatter.format(record) for record in caplog.records]
    assert any("HTTP 403" in line for line in lines), lines
    assert not any("sekret" in line for line in lines), lines


def test_log_lines_mask_credentials_in_urls() -> None:
    from app.logging import redact

    url = "https://api.mouser.com/x?apiKey=abc123&q=1 https://e14/p?callInfo.apiKey=def&x=2"
    assert (
        redact(url)
        == "https://api.mouser.com/x?apiKey=***&q=1 https://e14/p?callInfo.apiKey=***&x=2"
    )
