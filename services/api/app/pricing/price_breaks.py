"""Price-break and purchase-quantity arithmetic (pure). Used by offer selection and the
impact engine, so every price in the product comes from one place."""

from collections.abc import Sequence
from decimal import ROUND_CEILING, Decimal

from app.domain.models import PriceBreak


def unit_price_at(breaks: Sequence[PriceBreak], qty: int) -> Decimal | None:
    """Price of the highest break whose quantity is ≤ `qty`.

    None when `qty` is below the first break: there is no published price for that
    quantity, and it must be shown as unavailable, never estimated.
    """
    eligible = [b for b in breaks if b.qty <= qty]
    return max(eligible, key=lambda b: b.qty).unit_price if eligible else None


def buy_quantity(need: Decimal, moq: int | None, multiple: int | None) -> int:
    """Smallest orderable quantity covering `need`: ≥ MOQ and a whole number of multiples."""
    if need <= 0:
        return 0
    step = multiple or 1
    packs = (need / step).to_integral_value(rounding=ROUND_CEILING)
    return max(int(packs) * step, moq or 1)


def next_break_saving(
    breaks: Sequence[PriceBreak], qty: int, moq: int | None, multiple: int | None
) -> tuple[int, Decimal] | None:
    """Cheapest larger order quantity (a later price break) with a lower *total* cost than
    buying `qty`, as (quantity, saving). None if buying more never costs less."""
    base_price = unit_price_at(breaks, qty)
    if base_price is None:
        return None
    base_total = base_price * qty
    best: tuple[int, Decimal] | None = None
    for b in breaks:
        if b.qty <= qty:
            continue
        order = buy_quantity(Decimal(b.qty), moq, multiple)
        price = unit_price_at(breaks, order)
        if price is None:
            continue
        saving = base_total - price * order
        if saving > 0 and (best is None or saving > best[1]):
            best = (order, saving)
    return best
