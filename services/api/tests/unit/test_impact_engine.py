"""Impact engine: expected values below are worked out by hand from the formulas."""

import itertools
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.enums import Provenance, SourceMode
from app.domain.facts import actual, unavailable
from app.domain.models import Adders, Assumptions, BomLine, Offer, PriceBreak, ScrapPolicy
from app.impact.engine import LineOverride, compute_line, compute_project

NOW = datetime(2026, 10, 17, tzinfo=UTC)
FIXED_2PCT = Assumptions(scrap_policy=ScrapPolicy(mode="fixed", fixed_pct=Decimal("0.02")))


def _line(line_id: str = "ln_1", qty: Decimal | None = Decimal(3), **kw: object) -> BomLine:
    fact = (
        actual(qty, "ev_bom") if qty is not None else unavailable("Quantity 'TBD' is not a number")
    )
    return BomLine(
        id=line_id, line_no=1, mpn="P1", qty_per=fact, selected_offer_id=f"off_{line_id}", **kw
    )  # type: ignore[arg-type]


def _offer(
    line_id: str = "ln_1",
    *,
    moq: int = 1,
    mult: int = 1,
    stock: int | None = 10_000,
    breaks: tuple[tuple[int, str], ...] = ((1, "1.00"), (100, "0.50"), (1000, "0.20")),
    currency: str = "USD",
) -> Offer:
    return Offer(
        id=f"off_{line_id}",
        line_id=line_id,
        distributor="D",
        sku="S",
        mpn="P1",
        manufacturer="M",
        stock=stock,
        moq=moq,
        order_multiple=mult,
        currency=currency,
        evidence_id="ev_off",
        mode=SourceMode.DEMO_SNAPSHOT,
        fetched_at=NOW,
        price_breaks=[PriceBreak(qty=q, unit_price=Decimal(p)) for q, p in breaks],
    )


def test_cut_tape_line() -> None:
    # required 3×100 = 300; gross ceil(300×1.02) = 306; buy 306 @ 0.50 = 153.00
    c = compute_line(_line(), _offer(), 100, FIXED_2PCT, "USD")
    i = c.impact
    assert (i.required.value, i.gross.value, i.buy_qty.value) == (300, 306, 306)
    assert i.unit_price.value == Decimal("0.50")
    assert i.unit_price.provenance is Provenance.ACTUAL
    assert i.unit_price.evidence_ids == ("ev_off",)
    assert i.extended.value == Decimal("153.00")
    assert i.excess_qty.value == 0
    assert i.per_unit_cost.value == Decimal("1.5300")
    assert c.scrap_cost == Decimal("3.00")  # 6 scrap units × 0.50
    assert i.scrap_pct.provenance is Provenance.ASSUMED
    assert [step.label for step in i.trace][:4] == [
        "Required",
        "Scrap allowance",
        "Gross need",
        "Net need",
    ]


def test_reel_moq_creates_excess() -> None:
    offer = _offer(moq=500, mult=500, breaks=((500, "0.70"), (1000, "0.64")))
    i = compute_line(_line(qty=Decimal(1)), offer, 100, FIXED_2PCT, "USD").impact
    assert (i.net_need.value, i.buy_qty.value, i.excess_qty.value) == (102, 500, 398)
    assert i.excess_cost.value == Decimal("278.60")  # 398 × 0.70
    assert i.extended.value == Decimal("350.00")


def test_shortage_against_stock() -> None:
    i = compute_line(_line(), _offer(stock=37), 100, FIXED_2PCT, "USD").impact
    assert i.shortage_qty.value == 306 - 37
    unknown = compute_line(_line(), _offer(stock=None), 100, FIXED_2PCT, "USD").impact
    assert unknown.shortage_qty.provenance is Provenance.UNAVAILABLE


def test_on_hand_override_reduces_purchase() -> None:
    i = compute_line(_line(), _offer(), 100, FIXED_2PCT, "USD", LineOverride(on_hand=200)).impact
    assert (i.net_need.value, i.buy_qty.value) == (106, 106)
    assert i.unit_price.value == Decimal("0.50")


def test_missing_inputs_are_unavailable_never_zero() -> None:
    no_qty = compute_line(_line(qty=None), _offer(), 100, FIXED_2PCT, "USD").impact
    assert no_qty.extended.provenance is Provenance.UNAVAILABLE
    assert "TBD" in (no_qty.extended.note or "")

    no_offer = compute_line(_line(), None, 100, FIXED_2PCT, "USD").impact
    assert no_offer.required.value == 300  # what is known is still shown
    assert no_offer.extended.value is None

    below_first_break = _offer(breaks=((1000, "0.20"),))
    i = compute_line(_line(), below_first_break, 100, FIXED_2PCT, "USD").impact
    assert i.unit_price.provenance is Provenance.UNAVAILABLE
    assert "no price for 306" in (i.unit_price.note or "")

    no_fx = compute_line(_line(), _offer(currency="EUR"), 100, FIXED_2PCT, "USD").impact
    assert "exchange rate" in (no_fx.unit_price.note or "")


def test_fx_conversion_is_calculated() -> None:
    assumptions = FIXED_2PCT.model_copy(update={"fx_overrides": {"USD->INR": Decimal("83")}})
    i = compute_line(_line(), _offer(), 100, assumptions, "INR").impact
    assert i.unit_price.value == Decimal("41.50")
    assert i.unit_price.provenance is Provenance.CALCULATED


def test_price_tier_scrap_uses_orderable_price() -> None:
    reel = _offer(moq=500, mult=500, breaks=((500, "0.70"),))
    i = compute_line(_line(qty=Decimal(1)), reel, 100, Assumptions(), "USD").impact
    assert i.scrap_pct.value == Decimal("0.02")  # 0.70 is in the ≥ 0.25 tier


def test_break_jump_recommendation() -> None:
    # 1 × 900 boards: gross 918 @ 0.50 = 459.00 vs 1,000 @ 0.20 = 200.00 → saves 259.00
    c = compute_line(_line(qty=Decimal(1)), _offer(), 900, FIXED_2PCT, "USD")
    assert c.recommendation is not None
    assert c.recommendation.saving.value == Decimal("259.00")
    assert c.recommendation.saving.provenance is Provenance.RECOMMENDED
    assert c.recommendation.message.startswith("P1: order 1,000 instead of 918")


def test_project_totals_contributions_and_adders() -> None:
    lines = [_line("a"), _line("b", qty=Decimal(1)), _line("c", qty=None), _line("d", dnp=True)]
    offers = {o.id: o for o in (_offer("a"), _offer("b"), _offer("c"), _offer("d"))}
    assumptions = FIXED_2PCT.model_copy(
        update={
            "adders": Adders(
                assembly_per_unit=Decimal(2),
                nre=Decimal(500),
                overhead_pct=Decimal("0.10"),
                margin_pct=Decimal("0.20"),
            )
        }
    )
    result = compute_project(lines, offers, 100, assumptions, "USD")

    # a: 306 @ 0.50 = 153.00; b: 102 @ 0.50 = 51.00 → material 204.00 (c unpriced, d DNP)
    assert result.totals.material.value == Decimal("204.00")
    assert result.unpriced_line_ids == ["c"]
    assert result.totals.material.note == "Excludes 1 unpriced line(s)"
    assert {i.line_id for i in result.lines} == {"a", "b", "c"}
    shares = [
        i.contribution_pct.value for i in result.lines if i.contribution_pct.value is not None
    ]
    assert sum(shares) == Decimal("1.0000")
    # assembly 200 + NRE 500 + overhead 20.40 = 720.40; margin 20% of 924.40 = 184.88
    assert result.totals.adders.value == Decimal("905.28")
    assert result.totals.grand_total.value == Decimal("1109.28")
    assert [step.label for step in result.waterfall][-1] == "Total"


def test_no_adders_is_an_explicit_assumption() -> None:
    result = compute_project([_line()], {"off_ln_1": _offer()}, 10, FIXED_2PCT, "USD")
    assert result.totals.adders.provenance is Provenance.ASSUMED
    assert result.totals.adders.value == 0


def test_purchase_invariants_hold_across_inputs() -> None:
    for qty, volume, moq, mult in itertools.product(
        (1, 3, 7), (1, 99, 1000), (1, 50, 500), (1, 25, 500)
    ):
        if moq % mult:
            continue
        offer = _offer(moq=moq, mult=mult, breaks=((moq, "1.00"),))
        i = compute_line(_line(qty=Decimal(qty)), offer, volume, FIXED_2PCT, "USD").impact
        buy, net = i.buy_qty.value, i.net_need.value
        assert buy is not None
        assert net is not None
        assert buy >= net
        assert buy >= moq
        assert buy % mult == 0
        assert i.excess_qty.value == buy - net


def test_scrap_policy_modes() -> None:
    line_0402 = _line(package="0402")
    package = Assumptions(scrap_policy=ScrapPolicy(mode="package"))
    assert compute_line(line_0402, _offer(), 10, package, "USD").impact.scrap_pct.value == Decimal(
        "0.03"
    )
    ic = _line(package="QFN-32")
    assert compute_line(ic, _offer(), 10, package, "USD").impact.scrap_pct.value == Decimal("0.005")
    override = compute_line(
        _line(), _offer(), 10, package, "USD", LineOverride(scrap_pct=Decimal(0))
    )
    assert override.impact.scrap_pct.value == 0
    assert "What-if" in (override.impact.scrap_pct.note or "")
    cheap = _offer(breaks=((1, "0.01"),))
    tiered = compute_line(_line(), cheap, 10, Assumptions(), "USD").impact.scrap_pct
    assert tiered.value == Decimal("0.05")
    assert "0.25" not in (tiered.note or "")
