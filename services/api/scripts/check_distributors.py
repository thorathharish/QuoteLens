"""Check live distributor credentials and parsing for one part (prints offers, never secrets).

uv run python scripts/check_distributors.py RC0603FR-0710KL
"""

import asyncio
import sys

from app.config import get_settings
from app.domain.mpn import normalize_mpn
from app.sourcing.providers.live import build_live_providers


def _stock(stock: int | None) -> str:
    return "unknown" if stock is None else f"{stock:,}"


async def main(raw: str) -> int:
    mpn = normalize_mpn(raw)
    if mpn is None:
        print("Give a part number")
        return 2
    providers = build_live_providers(get_settings())
    if not providers:
        print("No distributor credentials configured (see .env.example)")
        return 2
    results = await asyncio.gather(*(p.fetch([mpn]) for p in providers))
    for provider, result in zip(providers, results, strict=True):
        offers = result.offers.get(mpn, [])
        component = result.components.get(mpn)
        print(
            f"\n{provider.name}: {len(offers)} offer(s)"
            + (f", lifecycle {component.lifecycle.value}" if component else ", part not found")
            + (f", errors: {result.errors}" if result.errors else "")
        )
        for offer in offers:
            first = offer.price_breaks[0]
            print(
                f"  {offer.sku:<28} stock {_stock(offer.stock):>9}  MOQ {offer.moq:>6,}  "
                f"lead {offer.lead_days if offer.lead_days is not None else '?':>4} d  "
                f"{first.qty:>5,} @ {first.price} {offer.currency}  ({offer.packaging})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "RC0603FR-0710KL")))
