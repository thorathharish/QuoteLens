"""Manufacturing impact (LLD §3.5): per line and per build volume, then rolled up.

    required   = qty_per × volume
    gross      = ceil(required × (1 + scrap))           scrap is an ASSUMED allowance
    net_need   = max(0, gross − on_hand)                on_hand defaults to 0 (assumed)
    buy_qty    = max(MOQ, ceil(net_need / multiple) × multiple)
    unit_price = price break at buy_qty (converted to the project currency if needed)
    extended   = buy_qty × unit_price;  excess = buy_qty − net_need;  shortage = buy_qty − stock

Every step is a CalcStep in the line's trace. Missing inputs make the dependent values
UNAVAILABLE with a reason; nothing is ever silently priced at 0. Pure: no I/O.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from pydantic import JsonValue

from app.domain.enums import Provenance
from app.domain.facts import Fact, actual, assumed, calculated, recommended, unavailable
from app.domain.models import Assumptions, BomLine, CalcStep, LineImpact, Offer
from app.impact.models import (
    ImpactRecommendation,
    ImpactResult,
    ImpactTotals,
    RecommendationKind,
    WaterfallStep,
)
from app.impact.scrap_policy import scrap_allowance
from app.pricing.fx import convert
from app.pricing.price_breaks import buy_quantity, next_break_saving, unit_price_at

CENT = Decimal("0.01")
Converter = Callable[[Decimal], Decimal | None]
MILLI = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class LineOverride:
    """What-if inputs for one line (never persisted)."""

    scrap_pct: Decimal | None = None
    offer_id: str | None = None
    qty_per: Decimal | None = None
    on_hand: int | None = None


@dataclass
class LineComputation:
    impact: LineImpact
    required_cost: Decimal | None = None
    scrap_cost: Decimal | None = None
    recommendation: ImpactRecommendation | None = None
    trace: list[CalcStep] = field(default_factory=list)


def num(value: Decimal | int) -> str:
    """Human-readable number for formulas: no exponent notation, thousands separators."""
    d = Decimal(value)
    if d == d.to_integral():
        return f"{d:,.0f}"
    return f"{d.normalize():,f}"


def money(value: Decimal, currency: str) -> str:
    return f"{currency} {value.quantize(CENT, ROUND_HALF_UP):,}"


def _ceil(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)


def _unavailable_impact(
    line: BomLine,
    volume: int,
    reason: str,
    *,
    required: Fact[Decimal],
    scrap: Fact[Decimal],
    trace: list[CalcStep],
) -> LineComputation:
    na: Fact[Decimal] = unavailable(reason)
    return LineComputation(
        impact=LineImpact(
            line_id=line.id,
            volume=volume,
            required=required,
            scrap_pct=scrap,
            gross=na,
            net_need=na,
            buy_qty=na,
            excess_qty=na,
            shortage_qty=na,
            unit_price=na,
            extended=na,
            excess_cost=na,
            per_unit_cost=na,
            contribution_pct=na,
            trace=trace,
        )
    )


def compute_line(
    line: BomLine,
    offer: Offer | None,
    volume: int,
    assumptions: Assumptions,
    currency: str,
    override: LineOverride | None = None,
) -> LineComputation:
    override = override or LineOverride()
    trace: list[CalcStep] = []

    def step(label: str, fact: Fact[Decimal], **inputs: JsonValue) -> Fact[Decimal]:
        trace.append(
            CalcStep(
                label=label, formula=fact.formula or fact.note or "", inputs=inputs, output=fact
            )
        )
        return fact

    qty = override.qty_per if override.qty_per is not None else line.qty_per.value
    if qty is None:
        reason = line.qty_per.note or "Quantity per assembly is unavailable"
        na: Fact[Decimal] = unavailable(reason)
        return _unavailable_impact(line, volume, reason, required=na, scrap=na, trace=trace)

    qty_evidence = line.qty_per.evidence_ids
    required = step(
        "Required",
        calculated(qty * volume, f"{num(qty)} per assembly × {num(volume)}", *qty_evidence),
        qty_per=str(qty),
        volume=volume,
    )
    required_value = qty * volume

    def native_to_project(amount: Decimal) -> Decimal | None:
        return (
            convert(amount, offer.currency, currency, assumptions.fx_overrides) if offer else None
        )

    tier_price = None
    if offer is not None:
        # Tier on the price actually payable: at least the MOQ / one pack.
        orderable = buy_quantity(required_value, offer.moq, offer.order_multiple) or 1
        native = unit_price_at(offer.price_breaks, orderable)
        tier_price = native_to_project(native) if native is not None else None
    scrap = step(
        "Scrap allowance",
        scrap_allowance(line, assumptions.scrap_policy, tier_price, override.scrap_pct),
    )
    scrap_value = scrap.value or Decimal(0)

    if offer is None:
        reason = _no_offer_reason(line)
        return _unavailable_impact(
            line, volume, reason, required=required, scrap=scrap, trace=trace
        )

    gross_value = _ceil(required_value * (1 + scrap_value))
    gross = step(
        "Gross need",
        calculated(gross_value, f"ceil({num(required_value)} × (1 + {scrap_value:.1%}))"),
    )
    on_hand = Decimal(override.on_hand or 0)
    net_value = max(Decimal(0), gross_value - on_hand)
    on_hand_label = num(on_hand) if override.on_hand is not None else "0 (assumed: none in stock)"
    net = step(
        "Net need",
        calculated(net_value, f"max(0, {num(gross_value)} − {num(on_hand)} on hand)"),
        on_hand=on_hand_label,
    )

    multiple = offer.order_multiple or 1
    buy_value = Decimal(buy_quantity(net_value, offer.moq, offer.order_multiple))
    buy = step(
        "Buy quantity",
        calculated(
            buy_value,
            f"max(MOQ {num(offer.moq or 1)}, "
            f"ceil({num(net_value)} ÷ {num(multiple)}) × {num(multiple)})",
            offer.evidence_id,
        ),
    )

    native_price = unit_price_at(offer.price_breaks, int(buy_value))
    if native_price is None:
        reason = f"{offer.distributor} publishes no price for {num(buy_value)} units"
        return _unavailable_impact(
            line, volume, reason, required=required, scrap=scrap, trace=trace
        )
    price_value = native_to_project(native_price)
    if price_value is None:
        reason = f"No {offer.currency}->{currency} exchange rate in the assumptions"
        return _unavailable_impact(
            line, volume, reason, required=required, scrap=scrap, trace=trace
        )
    unit_price: Fact[Decimal] = (
        actual(price_value, offer.evidence_id, unit=currency)
        if offer.currency == currency
        else calculated(
            price_value, f"{native_price} {offer.currency} × FX", offer.evidence_id, unit=currency
        )
    )
    step(f"Unit price at {num(buy_value)} ({offer.distributor})", unit_price)

    extended_value = buy_value * price_value
    extended = step(
        "Extended cost",
        calculated(
            extended_value, f"{num(buy_value)} × {price_value}", offer.evidence_id, unit=currency
        ),
    )
    excess_value = buy_value - net_value
    excess_qty = step(
        "MOQ/pack excess", calculated(excess_value, f"{num(buy_value)} − {num(net_value)}")
    )
    excess_cost = step(
        "Excess cost",
        calculated(
            excess_value * price_value, f"{num(excess_value)} × {price_value}", unit=currency
        ),
    )
    if offer.stock is None:
        shortage: Fact[Decimal] = unavailable(f"{offer.distributor} does not report stock")
    else:
        shortage_value = max(Decimal(0), buy_value - offer.stock)
        shortage = calculated(
            shortage_value,
            f"max(0, {num(buy_value)} − {num(offer.stock)} in stock)",
            offer.evidence_id,
        )
    step("Shortage vs stock", shortage)
    per_unit = calculated(
        (extended_value / volume).quantize(MILLI, ROUND_HALF_UP),
        f"{money(extended_value, currency)} ÷ {num(volume)}",
        unit=currency,
    )

    computation = LineComputation(
        impact=LineImpact(
            line_id=line.id,
            volume=volume,
            required=required,
            scrap_pct=scrap,
            gross=gross,
            net_need=net,
            buy_qty=buy,
            excess_qty=excess_qty,
            shortage_qty=shortage,
            unit_price=unit_price,
            extended=extended,
            excess_cost=excess_cost,
            per_unit_cost=per_unit,
            contribution_pct=unavailable("Computed with the BOM total"),
            trace=trace,
        ),
        required_cost=required_value * price_value,
        scrap_cost=(gross_value - required_value) * price_value,
    )
    computation.recommendation = _break_jump(
        line, offer, int(buy_value), net_value, extended_value, currency, native_to_project
    )
    return computation


def _no_offer_reason(line: BomLine) -> str:
    if line.recommendation and line.recommendation.reasons:
        return f"No offer selected: {line.recommendation.reasons[0]}"
    return "No offer selected: the part has not been sourced"


def _break_jump(
    line: BomLine,
    offer: Offer,
    buy: int,
    net: Decimal,
    extended: Decimal,
    currency: str,
    to_project: Converter,
) -> ImpactRecommendation | None:
    jump = next_break_saving(offer.price_breaks, buy, offer.moq, offer.order_multiple)
    if jump is None:
        return None
    order_qty, native_saving = jump
    saving = to_project(native_saving)
    if saving is None or saving < CENT:
        return None
    spare = Decimal(order_qty) - net
    message = (
        f"{line.mpn}: order {num(order_qty)} instead of {num(buy)} at {offer.distributor}; "
        f"the next price break saves {money(saving, currency)} and leaves {num(spare)} spare"
    )
    return ImpactRecommendation(
        line_id=line.id,
        kind=RecommendationKind.PRICE_BREAK_JUMP,
        message=message,
        saving=recommended(
            saving.quantize(CENT, ROUND_HALF_UP), message, offer.evidence_id, unit=currency
        ),
    )


def compute_project(
    lines: Sequence[BomLine],
    offers_by_id: dict[str, Offer],
    volume: int,
    assumptions: Assumptions,
    currency: str,
    overrides: dict[str, LineOverride] | None = None,
) -> ImpactResult:
    overrides = overrides or {}
    computations: list[LineComputation] = []
    for line in lines:
        if line.dnp:
            continue
        override = overrides.get(line.id)
        offer_id = override.offer_id if override and override.offer_id else line.selected_offer_id
        offer = offers_by_id.get(offer_id) if offer_id else None
        if offer is not None and offer.line_id != line.id:
            offer = None
        computations.append(compute_line(line, offer, volume, assumptions, currency, override))

    priced = [c for c in computations if c.impact.extended.is_available]
    unpriced = [c.impact.line_id for c in computations if not c.impact.extended.is_available]
    note = f"Excludes {len(unpriced)} unpriced line(s)" if unpriced else None
    material_value = sum((c.impact.extended.value or Decimal(0) for c in priced), Decimal(0))

    if not priced:
        na: Fact[Decimal] = unavailable("No line could be priced")
        totals = ImpactTotals(
            required_material=na,
            scrap_cost=na,
            excess_cost=na,
            material=na,
            adders=na,
            grand_total=na,
            per_unit=na,
        )
        return ImpactResult(
            volume=volume,
            currency=currency,
            totals=totals,
            waterfall=[],
            lines=[c.impact for c in computations],
            recommendations=[],
            unpriced_line_ids=unpriced,
        )

    def total(values: list[Decimal], label: str) -> Fact[Decimal]:
        return Fact[Decimal](
            value=sum(values, Decimal(0)).quantize(CENT, ROUND_HALF_UP),
            unit=currency,
            provenance=Provenance.CALCULATED,
            formula=f"Σ {label} over {len(values)} priced lines",
            note=note,
        )

    required_cost = total([c.required_cost or Decimal(0) for c in priced], "required × unit price")
    scrap_cost = total([c.scrap_cost or Decimal(0) for c in priced], "scrap allowance cost")
    excess_cost = total(
        [c.impact.excess_cost.value or Decimal(0) for c in priced], "MOQ/pack excess cost"
    )
    material = total([c.impact.extended.value or Decimal(0) for c in priced], "extended cost")
    adders = _adders(assumptions, volume, material_value, currency)
    grand_value = (material_value + (adders.value or Decimal(0))).quantize(CENT, ROUND_HALF_UP)
    grand_total = calculated(grand_value, "material + adders", unit=currency)
    if note:
        grand_total = grand_total.model_copy(update={"note": note})
    per_unit = calculated(
        (grand_value / volume).quantize(MILLI, ROUND_HALF_UP),
        f"{money(grand_value, currency)} ÷ {num(volume)}",
        unit=currency,
    )

    impacts = []
    for c in computations:
        impact = c.impact
        if impact.extended.is_available and material_value:
            share = ((impact.extended.value or Decimal(0)) / material_value).quantize(
                MILLI, ROUND_HALF_UP
            )
            impact = impact.model_copy(
                update={
                    "contribution_pct": calculated(
                        share,
                        f"{money(impact.extended.value or Decimal(0), currency)} ÷ "
                        f"{money(material_value, currency)}",
                    )
                }
            )
        impacts.append(impact)

    return ImpactResult(
        volume=volume,
        currency=currency,
        totals=ImpactTotals(
            required_material=required_cost,
            scrap_cost=scrap_cost,
            excess_cost=excess_cost,
            material=material,
            adders=adders,
            grand_total=grand_total,
            per_unit=per_unit,
        ),
        waterfall=[
            WaterfallStep(label="Required material", value=required_cost),
            WaterfallStep(label="Scrap allowance", value=scrap_cost),
            WaterfallStep(label="MOQ / pack excess", value=excess_cost),
            WaterfallStep(label="Adders", value=adders),
            WaterfallStep(label="Total", value=grand_total),
        ],
        lines=impacts,
        recommendations=sorted(
            (c.recommendation for c in computations if c.recommendation),
            key=lambda r: r.saving.value or Decimal(0),
            reverse=True,
        ),
        unpriced_line_ids=unpriced,
    )


def _adders(
    assumptions: Assumptions, volume: int, material: Decimal, currency: str
) -> Fact[Decimal]:
    a = assumptions.adders
    if all(v is None for v in (a.assembly_per_unit, a.nre, a.overhead_pct, a.margin_pct)):
        return assumed(
            Decimal(0), "No adders entered (assembly, NRE, overhead, margin)", unit=currency
        )
    assembly = (a.assembly_per_unit or Decimal(0)) * volume
    nre = a.nre or Decimal(0)
    overhead = (a.overhead_pct or Decimal(0)) * material
    subtotal = material + assembly + nre + overhead
    margin = (a.margin_pct or Decimal(0)) * subtotal
    value = (assembly + nre + overhead + margin).quantize(CENT, ROUND_HALF_UP)
    formula = (
        f"assembly {money(assembly, currency)} + NRE {money(nre, currency)} + overhead "
        f"{money(overhead, currency)} + margin {money(margin, currency)}"
    )
    return calculated(value, formula, unit=currency)
