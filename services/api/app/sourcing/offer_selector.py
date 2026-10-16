"""Recommend the best offer for a line, with human-readable reasons.

Not cheapest-price-only (a flaw in the reference implementation). The score weighs:
  0.45 total cost at the buy quantity (MOQ/pack rounding included)
  0.25 stock coverage of the buy quantity
  0.20 lead time (full marks when stock covers the order)
  0.10 packaging fit (little or no excess forced by MOQ/multiples)
Unauthorized, obsolete and unpriceable offers are excluded, and every exclusion is
explained when nothing remains. Deterministic: ties break on distributor name.
"""

from dataclasses import dataclass, replace
from decimal import Decimal

from app.domain.enums import Lifecycle
from app.domain.models import Offer, OfferRecommendation
from app.pricing.fx import convert
from app.pricing.price_breaks import buy_quantity, unit_price_at

WEIGHTS = {"cost": 0.45, "stock": 0.25, "lead": 0.20, "packaging": 0.10}
LEAD_HORIZON_DAYS = 180
UNKNOWN_LEAD_SCORE = 0.3


@dataclass(frozen=True, slots=True)
class ScoredOffer:
    offer: Offer
    buy_qty: int
    unit_price: Decimal
    total: Decimal
    stock_coverage: float
    lead_score: float
    packaging_fit: float
    score: float = 0.0


def money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def qty(value: Decimal | int) -> str:
    number = Decimal(value)
    return f"{number:,.0f}" if number == number.to_integral() else f"{number:,}"


def recommend_offer(
    offers: list[Offer],
    need: Decimal,
    volume: int,
    currency: str,
    fx_rates: dict[str, Decimal],
) -> OfferRecommendation:
    if need <= 0:
        return OfferRecommendation(
            offer_id=None,
            volume=volume,
            reasons=["Quantity is unavailable, so no offer can be priced"],
        )
    if not offers:
        return OfferRecommendation(
            offer_id=None, volume=volume, reasons=["No distributor offers found for this part"]
        )

    scored: list[ScoredOffer] = []
    excluded: list[str] = []
    for offer in offers:
        verdict = _evaluate(offer, need, currency, fx_rates)
        if isinstance(verdict, str):
            excluded.append(f"{offer.distributor}: {verdict}")
        else:
            scored.append(verdict)
    if not scored:
        return OfferRecommendation(
            offer_id=None, volume=volume, reasons=["No authorized, purchasable offer", *excluded]
        )

    cheapest = min(s.total for s in scored)
    ranked = sorted(
        (_with_score(s, cheapest) for s in scored),
        key=lambda s: (-s.score, s.offer.distributor, s.offer.sku),
    )
    best = ranked[0]
    return OfferRecommendation(
        offer_id=best.offer.id,
        score=round(best.score, 3),
        volume=volume,
        reasons=_reasons(best, ranked, need, currency),
    )


def _evaluate(
    offer: Offer, need: Decimal, currency: str, fx: dict[str, Decimal]
) -> ScoredOffer | str:
    if not offer.authorized:
        return "not an authorized distributor (traceability risk)"
    if offer.lifecycle is Lifecycle.OBSOLETE:
        return "part is obsolete"
    buy = buy_quantity(need, offer.moq, offer.order_multiple)
    native_price = unit_price_at(offer.price_breaks, buy)
    if native_price is None:
        return f"no price published for {qty(buy)} units"
    price = convert(native_price, offer.currency, currency, fx)
    if price is None:
        return f"no {offer.currency}->{currency} exchange rate in the assumptions"
    stock = offer.stock or 0
    coverage = min(1.0, stock / buy) if buy else 0.0
    if coverage >= 1:
        lead = 1.0
    elif offer.lead_time_days is None:
        lead = UNKNOWN_LEAD_SCORE
    else:
        lead = 1 - min(offer.lead_time_days, LEAD_HORIZON_DAYS) / LEAD_HORIZON_DAYS
    return ScoredOffer(
        offer=offer,
        buy_qty=buy,
        unit_price=price,
        total=price * buy,
        stock_coverage=coverage,
        lead_score=lead,
        packaging_fit=float(need / buy),
    )


def _with_score(s: ScoredOffer, cheapest: Decimal) -> ScoredOffer:
    cost = float(cheapest / s.total) if s.total else 1.0
    score = (
        WEIGHTS["cost"] * cost
        + WEIGHTS["stock"] * s.stock_coverage
        + WEIGHTS["lead"] * s.lead_score
        + WEIGHTS["packaging"] * s.packaging_fit
    )
    return replace(s, score=score)


def _reasons(
    best: ScoredOffer, ranked: list[ScoredOffer], need: Decimal, currency: str
) -> list[str]:
    reasons: list[str] = []
    stock = best.offer.stock or 0
    if best.stock_coverage >= 1:
        if best.buy_qty == need:
            reasons.append(f"In stock: covers all {qty(need)} needed ({qty(stock)} available)")
        else:
            reasons.append(
                f"In stock: covers the full order of {qty(best.buy_qty)} "
                f"({qty(need)} needed, {qty(stock)} available)"
            )
    else:
        lead = (
            f"factory lead time {best.offer.lead_time_days} days"
            if best.offer.lead_time_days is not None
            else "lead time unknown"
        )
        reasons.append(
            f"Stock covers only {best.stock_coverage:.0%} of {qty(best.buy_qty)}; {lead}"
        )

    others = [s for s in ranked[1:] if s.offer.distributor != best.offer.distributor]
    if others:
        cheapest_other = min(others, key=lambda s: s.total)
        delta = cheapest_other.total - best.total
        if delta > 0:
            reasons.append(
                f"Lowest total cost: {money(best.total, currency)}, "
                f"{money(delta, currency)} less than {cheapest_other.offer.distributor}"
            )
        elif delta < 0:
            reasons.append(
                f"Costs {money(-delta, currency)} more than "
                f"{cheapest_other.offer.distributor}, but has better availability"
            )
    else:
        reasons.append(f"Only eligible offer: {money(best.total, currency)} total")

    excess = best.buy_qty - need
    if excess > 0:
        reasons.append(f"MOQ/pack rounding buys {qty(excess)} extra units")
    else:
        reasons.append(f"{best.offer.packaging or 'Packaging'}: no MOQ excess")
    return reasons
