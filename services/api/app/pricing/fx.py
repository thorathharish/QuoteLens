"""Currency conversion. Rates are user-provided assumptions (Project.assumptions.fx_overrides,
keyed "USD->INR"); with no rate, conversion is unavailable rather than guessed."""

from decimal import Decimal


def fx_key(source: str, target: str) -> str:
    return f"{source}->{target}"


def convert(amount: Decimal, source: str, target: str, rates: dict[str, Decimal]) -> Decimal | None:
    if source == target:
        return amount
    rate = rates.get(fx_key(source, target))
    if rate is not None:
        return amount * rate
    inverse = rates.get(fx_key(target, source))
    if inverse:
        return amount / inverse
    return None
