from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.catalog.rows import CatalogComponent, CatalogOffer, CatalogPriceBreak
from app.domain.enums import DataMode, Lifecycle, MatchStatus, SourceMode
from app.domain.models import Offer, PriceBreak
from app.pricing.fx import convert
from app.pricing.price_breaks import buy_quantity, next_break_saving, unit_price_at
from app.sourcing.chain import OfferSourceChain
from app.sourcing.matcher import match_line
from app.sourcing.offer_selector import recommend_offer
from app.sourcing.providers.base import ProviderResult
from app.sourcing.providers.catalog import _suggest

NOW = datetime(2026, 10, 17, tzinfo=UTC)
BREAKS = [
    PriceBreak(qty=1, unit_price=Decimal("1.00")),
    PriceBreak(qty=100, unit_price=Decimal("0.50")),
    PriceBreak(qty=1000, unit_price=Decimal("0.20")),
]


# ── pricing ──────────────────────────────────────────────────


def test_unit_price_uses_highest_break_at_or_below_quantity() -> None:
    assert unit_price_at(BREAKS, 1) == Decimal("1.00")
    assert unit_price_at(BREAKS, 99) == Decimal("1.00")
    assert unit_price_at(BREAKS, 100) == Decimal("0.50")
    assert unit_price_at(BREAKS, 5000) == Decimal("0.20")
    assert unit_price_at(BREAKS[1:], 10) is None  # below the first break: unavailable


@pytest.mark.parametrize(
    ("need", "moq", "mult", "expected"),
    [
        (Decimal(1), 500, 500, 500),
        (Decimal(501), 500, 500, 1000),
        (Decimal(7), 1, 1, 7),
        (Decimal("2.5"), None, None, 3),
        (Decimal(0), 10, 10, 0),
        (Decimal(12), 10, 5, 15),
    ],
)
def test_buy_quantity_respects_moq_and_multiples(
    need: Decimal, moq: int | None, mult: int | None, expected: int
) -> None:
    assert buy_quantity(need, moq, mult) == expected


def test_next_break_saving_finds_cheaper_larger_order() -> None:
    # 900 @ 0.50 = 450.00 vs 1000 @ 0.20 = 200.00
    assert next_break_saving(BREAKS, 900, 1, 1) == (1000, Decimal("250.00"))
    assert next_break_saving(BREAKS, 1000, 1, 1) is None
    assert next_break_saving(BREAKS, 50, 1, 1) is None  # 100 @ 0.50 = 50 > 50 @ 1.00? equal → no


def test_fx_conversion_never_guesses() -> None:
    rates = {"USD->INR": Decimal("83")}
    assert convert(Decimal(2), "USD", "USD", {}) == Decimal(2)
    assert convert(Decimal(2), "USD", "INR", rates) == Decimal(166)
    assert convert(Decimal(166), "INR", "USD", rates) == Decimal(2)
    assert convert(Decimal(1), "EUR", "USD", rates) is None


# ── selection ────────────────────────────────────────────────


def _offer(
    dist: str,
    price: str,
    stock: int | None = 10_000,
    *,
    moq: int = 1,
    mult: int = 1,
    authorized: bool = True,
    lifecycle: Lifecycle = Lifecycle.ACTIVE,
    lead: int | None = 60,
    currency: str = "USD",
) -> Offer:
    return Offer(
        id=f"off_{dist}",
        line_id="ln_1",
        distributor=dist,
        sku=f"SKU-{dist}",
        mpn="P1",
        manufacturer="M",
        authorized=authorized,
        stock=stock,
        moq=moq,
        order_multiple=mult,
        lead_time_days=lead,
        lifecycle=lifecycle,
        currency=currency,
        evidence_id=f"ev_{dist}",
        mode=SourceMode.DEMO_SNAPSHOT,
        fetched_at=NOW,
        price_breaks=[PriceBreak(qty=moq, unit_price=Decimal(price))],
    )


def test_prefers_cheapest_when_availability_is_equal() -> None:
    rec = recommend_offer([_offer("A", "1.10"), _offer("B", "1.00")], Decimal(100), 100, "USD", {})
    assert rec.offer_id == "off_B"
    assert rec.score is not None
    assert any("Lowest total cost" in r for r in rec.reasons)


def test_stock_beats_a_cheaper_offer_that_cannot_ship() -> None:
    cheap_no_stock = _offer("Cheap", "0.90", stock=0, lead=150)
    in_stock = _offer("Stocked", "1.00")
    rec = recommend_offer([cheap_no_stock, in_stock], Decimal(500), 500, "USD", {})
    assert rec.offer_id == "off_Stocked"
    assert any("more than Cheap" in r and "better availability" in r for r in rec.reasons)


def test_moq_excess_is_part_of_total_cost_and_explained() -> None:
    reel = _offer("Reel", "0.50", moq=1000, mult=1000)
    cut = _offer("Cut", "0.80")
    rec = recommend_offer([reel, cut], Decimal(100), 100, "USD", {})
    assert rec.offer_id == "off_Cut"  # 100 x 0.80 = 80 beats 1000 x 0.50 = 500
    reel_only = recommend_offer([reel], Decimal(100), 100, "USD", {})
    assert any("900 extra units" in r for r in reel_only.reasons)
    assert any("full order of 1,000 (100 needed" in r for r in reel_only.reasons)


def test_exclusions_are_explained_when_nothing_is_eligible() -> None:
    offers = [
        _offer("Broker", "2.00", authorized=False),
        _offer("Dist", "1.00", lifecycle=Lifecycle.OBSOLETE),
        _offer("Euro", "1.00", currency="EUR"),
    ]
    rec = recommend_offer(offers, Decimal(10), 10, "USD", {})
    assert rec.offer_id is None
    text = " ".join(rec.reasons)
    assert "not an authorized distributor" in text
    assert "obsolete" in text
    assert "exchange rate" in text


def test_no_offers_or_no_quantity() -> None:
    assert recommend_offer([], Decimal(1), 1, "USD", {}).offer_id is None
    assert recommend_offer([_offer("A", "1")], Decimal(0), 1, "USD", {}).offer_id is None


def test_ties_are_deterministic() -> None:
    first = recommend_offer([_offer("B", "1.00"), _offer("A", "1.00")], Decimal(10), 10, "USD", {})
    second = recommend_offer([_offer("A", "1.00"), _offer("B", "1.00")], Decimal(10), 10, "USD", {})
    assert first.offer_id == second.offer_id == "off_A"


# ── matching and suggestions ─────────────────────────────────


def _component(mpn: str, mfr: str = "Texas Instruments") -> CatalogComponent:
    return CatalogComponent(
        mpn_norm=mpn,
        mpn=mpn,
        manufacturer=mfr,
        category="ic",
        description="d",
        source="test",
        snapshot_date=NOW.date(),
    )


def test_matching_is_exact_only_and_reports_candidates() -> None:
    components = {"TPS54331DDR": _component("TPS54331DDR")}
    hit = match_line("TPS54331DDR", "Texas Instruments", components, [])
    assert hit.status is MatchStatus.MATCHED
    assert hit.confidence == 1.0
    miss = match_line("TPS5431DDR", "Texas Instruments", components, ["TPS54331DDR"])
    assert miss.status is MatchStatus.NOT_FOUND
    assert miss.candidates == ["TPS54331DDR"]
    other_maker = match_line("TPS54331DDR", "Analog Devices", components, [])
    assert other_maker.confidence < 1.0
    assert match_line(None, None, components, []).status is MatchStatus.PENDING


def test_suggestions_cover_typos_and_missing_suffixes() -> None:
    known = ["TPS54331DDR", "GRM188R71H104KA93D", "RC0603FR-0710KL"]
    assert _suggest("TPS5431DDR", known, 3) == ["TPS54331DDR"]
    assert "GRM188R71H104KA93D" in _suggest("GRM188R71H104KA93", known, 3)
    assert _suggest("ZZZ999", known, 3) == []


# ── provider chain ───────────────────────────────────────────


def _catalog_offer(mpn: str, mode: SourceMode) -> CatalogOffer:
    return CatalogOffer(
        mpn_norm=mpn,
        distributor="D",
        sku=f"S-{mpn}",
        manufacturer="M",
        moq=1,
        mult=1,
        price_breaks=[CatalogPriceBreak(qty=1, price=Decimal(1))],
        currency="USD",
        fetched_at=NOW,
        mode=mode,
    )


class FakeProvider:
    def __init__(self, name: str, known: set[str], mode: SourceMode, fail: bool = False) -> None:
        self.name, self.known, self.mode, self.fail = name, known, mode, fail
        self.calls: list[list[str]] = []

    async def fetch(self, mpns: Sequence[str]) -> ProviderResult:
        self.calls.append(list(mpns))
        if self.fail:
            raise TimeoutError("down")
        return ProviderResult(
            offers={m: [_catalog_offer(m, self.mode)] for m in mpns if m in self.known}
        )

    async def suggest(self, mpn: str, limit: int = 3) -> list[str]:
        return []


async def test_cache_first_uses_live_only_for_missing_parts() -> None:
    cache = FakeProvider("catalog", {"A"}, SourceMode.CACHE)
    live = FakeProvider("live", {"A", "B"}, SourceMode.LIVE)
    result = await OfferSourceChain(cache, cache, [live]).fetch(["A", "B"], DataMode.CACHE_FIRST)
    assert live.calls == [["B"]]
    assert result.offers["A"][0].mode is SourceMode.CACHE
    assert result.offers["B"][0].mode is SourceMode.LIVE


async def test_live_first_falls_back_to_cache_and_reports_failures() -> None:
    cache = FakeProvider("catalog", {"A"}, SourceMode.CACHE)
    live = FakeProvider("live", {"A"}, SourceMode.LIVE, fail=True)
    result = await OfferSourceChain(cache, cache, [live]).fetch(["A"], DataMode.LIVE_FIRST)
    assert result.offers["A"][0].mode is SourceMode.CACHE
    assert result.errors == ["live unavailable (TimeoutError)"]


async def test_demo_snapshot_never_calls_live() -> None:
    cache = FakeProvider("catalog", {"A"}, SourceMode.DEMO_SNAPSHOT)
    live = FakeProvider("live", {"A"}, SourceMode.LIVE)
    await OfferSourceChain(cache, cache, [live]).fetch(["A"], DataMode.DEMO_SNAPSHOT)
    assert live.calls == []
