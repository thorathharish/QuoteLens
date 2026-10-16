"""Live distributor adapters: DigiKey (Product Information v4), Mouser (Search API v1) and
element14 (Product Search API). Each maps its response into provider-neutral catalog rows
with mode=LIVE and the distributor's product URL as the evidence reference.

Rules shared by all adapters:
- Only exact (normalized) manufacturer part numbers are accepted; fuzzy hits are dropped.
- Values a distributor does not state are left unknown, never guessed. (element14's
  lead-time field has an undocumented unit, so its lead time is reported as unknown.)
- One failing part or distributor never fails the BOM: errors are collected and reported.
"""

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.catalog.rows import CatalogComponent, CatalogOffer, CatalogPriceBreak
from app.config import Settings
from app.domain.enums import Lifecycle, SourceMode
from app.domain.mpn import normalize_mpn
from app.infra.http import CircuitBreaker, CircuitOpenError, request
from app.sourcing.providers.base import OfferProvider, ProviderResult

logger = logging.getLogger(__name__)

CONCURRENCY = 8
Lookup = tuple[list[CatalogOffer], CatalogComponent | None]


def _decimal(text: object) -> Decimal | None:
    cleaned = re.sub(r"[^0-9.]", "", str(text or ""))
    try:
        value = Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None
    return value if value is not None and value > 0 else None


def _int(text: object) -> int | None:
    digits = re.sub(r"[^0-9]", "", str(text or ""))
    return int(digits) if digits else None


def _breaks(pairs: list[tuple[int | None, Decimal | None]]) -> list[CatalogPriceBreak]:
    breaks = sorted({q: p for q, p in pairs if q and p}.items())
    return [CatalogPriceBreak(qty=q, price=p) for q, p in breaks]


class LiveProvider(ABC):
    name: str

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(self.name)

    async def fetch(self, mpns: Sequence[str]) -> ProviderResult:
        result = ProviderResult()
        semaphore = asyncio.Semaphore(CONCURRENCY)
        async with httpx.AsyncClient(headers={"Accept": "application/json"}) as client:

            async def one(mpn: str) -> None:
                async with semaphore:
                    try:
                        offers, component = await self.lookup(client, mpn)
                    except CircuitOpenError as exc:
                        result.errors.append(str(exc))
                        return
                    except Exception as exc:
                        logger.warning("%s lookup failed for %s", self.name, mpn, exc_info=True)
                        result.errors.append(f"{self.name} lookup failed ({type(exc).__name__})")
                        return
                    if offers:
                        result.offers.setdefault(mpn, []).extend(offers)
                    if component is not None:
                        result.components.setdefault(mpn, component)

            await asyncio.gather(*(one(m) for m in dict.fromkeys(mpns)))
        result.errors = list(dict.fromkeys(result.errors))
        return result

    @abstractmethod
    async def lookup(self, client: httpx.AsyncClient, mpn: str) -> Lookup: ...

    def _offer(self, **fields: Any) -> CatalogOffer | None:
        """Build a validated offer row; malformed distributor data is skipped, not guessed."""
        if not fields.get("price_breaks"):
            return None
        try:
            return CatalogOffer(
                distributor=self.name, mode=SourceMode.LIVE, fetched_at=datetime.now(UTC), **fields
            )
        except ValidationError:
            logger.warning("%s returned an offer that fails validation; skipped", self.name)
            return None

    def _component(self, **fields: Any) -> CatalogComponent | None:
        try:
            return CatalogComponent(
                source=f"{self.name} (live)", snapshot_date=date.today(), **fields
            )
        except ValidationError:
            return None


# ── DigiKey ──────────────────────────────────────────────────

_DIGIKEY_STATUS = {
    "active": Lifecycle.ACTIVE,
    "obsolete": Lifecycle.OBSOLETE,
    "not for new designs": Lifecycle.NRND,
    "last time buy": Lifecycle.LAST_TIME_BUY,
    "discontinued at digi-key": Lifecycle.UNKNOWN,  # distributor stopped, not the maker
}


class DigiKeyProvider(LiveProvider):
    name = "DigiKey"

    def __init__(self, client_id: str, client_secret: str, sandbox: bool = False) -> None:
        super().__init__()
        self._client_id = client_id
        self._client_secret = client_secret
        self._host = "https://sandbox-api.digikey.com" if sandbox else "https://api.digikey.com"
        self._token: tuple[str, float] | None = None
        self._token_lock = asyncio.Lock()

    async def _access_token(self, client: httpx.AsyncClient, refresh: bool = False) -> str:
        async with self._token_lock:
            if self._token and not refresh and self._token[1] > time.monotonic():
                return self._token[0]
            response = await request(
                client,
                self.breaker,
                "POST",
                f"{self._host}/v1/oauth2/token",
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            body = response.json()
            self._token = (
                body["access_token"],
                time.monotonic() + int(body.get("expires_in", 600)) - 60,
            )
            return self._token[0]

    async def lookup(self, client: httpx.AsyncClient, mpn: str) -> Lookup:
        url = f"{self._host}/products/v4/search/{quote(mpn, safe='')}/productdetails"
        for attempt in range(2):
            token = await self._access_token(client, refresh=attempt > 0)
            response = await request(
                client,
                self.breaker,
                "GET",
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-DIGIKEY-Client-Id": self._client_id,
                    "X-DIGIKEY-Locale-Currency": "USD",
                    "X-DIGIKEY-Locale-Site": "US",
                },
            )
            if response.status_code != 401:
                break
        if response.status_code == 404:
            return [], None
        response.raise_for_status()
        return self.parse(response.json(), mpn)

    def parse(self, body: dict[str, Any], mpn: str) -> Lookup:
        product = body.get("Product") or {}
        if normalize_mpn(product.get("ManufacturerProductNumber")) != mpn:
            return [], None
        maker = (product.get("Manufacturer") or {}).get("Name") or "Unknown"
        status = str((product.get("ProductStatus") or {}).get("Status", "")).casefold()
        lifecycle = (
            Lifecycle.EOL
            if product.get("EndOfLife")
            else _DIGIKEY_STATUS.get(status, Lifecycle.UNKNOWN)
        )
        weeks = _int(product.get("ManufacturerLeadWeeks"))
        currency = (body.get("SearchLocaleUsed") or {}).get("Currency", "USD")
        # Some API apps receive no inventory: then every quantity reads 0. Without a
        # QuantityAvailable field, stock is unknown rather than zero.
        reports_stock = "QuantityAvailable" in product
        offers = []
        for variation in product.get("ProductVariations") or []:
            package = str((variation.get("PackageType") or {}).get("Name", ""))
            if variation.get("MarketPlace") or "Digi-Reel" in package:
                continue  # marketplace sellers are third parties; Digi-Reel adds a reeling fee
            offer = self._offer(
                mpn_norm=mpn,
                sku=str(variation.get("DigiKeyProductNumber")),
                manufacturer=maker,
                stock=(_int(variation.get("QuantityAvailableforPackageType")) or 0)
                if reports_stock
                else None,
                moq=max(1, _int(variation.get("MinimumOrderQuantity")) or 1),
                mult=max(1, _int(variation.get("StandardPackage")) or 1)
                if "Reel" in package
                else 1,
                lead_days=weeks * 7 if weeks is not None else None,
                packaging=package or None,
                price_breaks=_breaks(
                    [
                        (_int(p.get("BreakQuantity")), _decimal(p.get("UnitPrice")))
                        for p in variation.get("StandardPricing") or []
                    ]
                ),
                currency=currency,
                authorized=True,
                lifecycle=lifecycle,
                source_url=product.get("ProductUrl"),
            )
            if offer:
                offers.append(offer)
        description = (product.get("Description") or {}).get("ProductDescription") or ""
        component = self._component(
            mpn_norm=mpn,
            mpn=product.get("ManufacturerProductNumber"),
            manufacturer=maker,
            category=str((product.get("Category") or {}).get("Name") or "unknown").casefold(),
            description=description,
            lifecycle=lifecycle,
            datasheet_url=product.get("DatasheetUrl"),
            params={
                p["ParameterText"]: p.get("ValueText")
                for p in (product.get("Parameters") or [])[:30]
                if p.get("ParameterText")
            },
        )
        return offers, component


# ── Mouser ───────────────────────────────────────────────────

_MOUSER_STATUS = {
    "new product": Lifecycle.ACTIVE,
    "new at mouser": Lifecycle.ACTIVE,
    "not recommended for new designs": Lifecycle.NRND,
    "end of life": Lifecycle.EOL,
    "obsolete": Lifecycle.OBSOLETE,
}


class MouserProvider(LiveProvider):
    name = "Mouser"
    URL = "https://api.mouser.com/api/v1/search/partnumber"

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key

    async def lookup(self, client: httpx.AsyncClient, mpn: str) -> Lookup:
        response = await request(
            client,
            self.breaker,
            "POST",
            self.URL,
            params={"apiKey": self._api_key},
            json={"SearchByPartRequest": {"mouserPartNumber": mpn, "partSearchOptions": "Exact"}},
        )
        response.raise_for_status()
        return self.parse(response.json(), mpn)

    def parse(self, body: dict[str, Any], mpn: str) -> Lookup:
        errors = body.get("Errors") or []
        if errors:
            raise RuntimeError(f"Mouser error: {errors[0].get('Message', 'unknown')}")
        offers: list[CatalogOffer] = []
        component: CatalogComponent | None = None
        for part in (body.get("SearchResults") or {}).get("Parts") or []:
            if normalize_mpn(part.get("ManufacturerPartNumber")) != mpn:
                continue
            status = str(part.get("LifecycleStatus") or "").casefold()
            lifecycle = _MOUSER_STATUS.get(
                status, Lifecycle.ACTIVE if not status else Lifecycle.UNKNOWN
            )
            breaks = part.get("PriceBreaks") or []
            offer = self._offer(
                mpn_norm=mpn,
                sku=str(part.get("MouserPartNumber")),
                manufacturer=part.get("Manufacturer") or "Unknown",
                stock=_int(part.get("AvailabilityInStock")) or 0,
                moq=max(1, _int(part.get("Min")) or 1),
                mult=max(1, _int(part.get("Mult")) or 1),
                lead_days=_int(part.get("LeadTime")),
                packaging=", ".join(
                    str(a.get("AttributeValue"))
                    for a in part.get("ProductAttributes") or []
                    if a.get("AttributeName") == "Packaging"
                )
                or None,
                price_breaks=_breaks(
                    [(_int(b.get("Quantity")), _decimal(b.get("Price"))) for b in breaks]
                ),
                currency=(breaks[0].get("Currency") if breaks else None) or "USD",
                authorized=True,
                lifecycle=lifecycle,
                source_url=part.get("ProductDetailUrl"),
            )
            if offer:
                offers.append(offer)
            component = component or self._component(
                mpn_norm=mpn,
                mpn=part.get("ManufacturerPartNumber"),
                manufacturer=part.get("Manufacturer") or "Unknown",
                category=str(part.get("Category") or "unknown").casefold(),
                description=part.get("Description") or "",
                lifecycle=lifecycle,
                datasheet_url=part.get("DataSheetUrl") or None,
            )
        return offers, component


# ── element14 / Farnell / Newark ─────────────────────────────

_E14_CURRENCY = {
    "in.element14.com": "INR",
    "uk.farnell.com": "GBP",
    "www.newark.com": "USD",
    "sg.element14.com": "SGD",
    "au.element14.com": "AUD",
    "de.farnell.com": "EUR",
    "fr.farnell.com": "EUR",
    "nl.farnell.com": "EUR",
    "ie.farnell.com": "EUR",
}
_E14_STATUS = {
    "STOCKED": Lifecycle.ACTIVE,
    "DIRECT_SHIP": Lifecycle.ACTIVE,
    "ON_DEMAND": Lifecycle.ACTIVE,
    "PRE_RELEASE": Lifecycle.ACTIVE,
    "NO_LONGER_MANUFACTURED": Lifecycle.OBSOLETE,
    "NO_LONGER_STOCKED": Lifecycle.UNKNOWN,
}


class Element14Provider(LiveProvider):
    name = "element14"
    URL = "https://api.element14.com/catalog/products"

    def __init__(self, api_key: str, store: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._store = store
        self._currency = _E14_CURRENCY.get(store)

    async def lookup(self, client: httpx.AsyncClient, mpn: str) -> Lookup:
        response = await request(
            client,
            self.breaker,
            "GET",
            self.URL,
            params={
                "term": f"manuPartNum:{mpn}",
                "storeInfo.id": self._store,
                "resultsSettings.offset": 0,
                "resultsSettings.numberOfResults": 5,
                "resultsSettings.responseGroup": "large",
                "callInfo.responseDataFormat": "JSON",
                "callInfo.apiKey": self._api_key,
            },
        )
        response.raise_for_status()
        return self.parse(response.json(), mpn)

    def parse(self, body: dict[str, Any], mpn: str) -> Lookup:
        if self._currency is None:
            return [], None  # unknown store currency: prices could not be interpreted honestly
        products = (body.get("manufacturerPartNumberSearchReturn") or {}).get("products") or []
        offers: list[CatalogOffer] = []
        component: CatalogComponent | None = None
        for product in products:
            if normalize_mpn(product.get("translatedManufacturerPartNumber")) != mpn:
                continue
            lifecycle = _E14_STATUS.get(str(product.get("productStatus")), Lifecycle.UNKNOWN)
            maker = product.get("brandName") or product.get("vendorName") or "Unknown"
            offer = self._offer(
                mpn_norm=mpn,
                sku=str(product.get("sku")),
                manufacturer=maker,
                stock=_int((product.get("stock") or {}).get("level")) or 0,
                moq=max(1, _int(product.get("translatedMinimumOrderQuality")) or 1),
                mult=max(1, _int(product.get("packSize")) or 1),
                lead_days=None,  # leastLeadTime's unit is undocumented: do not guess
                packaging=product.get("unitOfMeasure"),
                price_breaks=_breaks(
                    [
                        (_int(p.get("from")), _decimal(p.get("cost")))
                        for p in product.get("prices") or []
                    ]
                ),
                currency=self._currency,
                authorized=True,
                lifecycle=lifecycle,
                source_url=f"https://{self._store}/{product.get('sku')}",
            )
            if offer:
                offers.append(offer)
            component = component or self._component(
                mpn_norm=mpn,
                mpn=product.get("translatedManufacturerPartNumber"),
                manufacturer=maker,
                category="unknown",
                description=product.get("displayName") or "",
                lifecycle=lifecycle,
            )
        return offers, component


def build_live_providers(settings: Settings) -> list[OfferProvider]:
    """Providers whose credentials are configured (blank values are treated as absent)."""
    providers: list[OfferProvider] = []
    configured = settings.configured_distributors
    if "DigiKey" in configured and settings.digikey_client_id and settings.digikey_client_secret:
        providers.append(
            DigiKeyProvider(
                settings.digikey_client_id.get_secret_value(),
                settings.digikey_client_secret.get_secret_value(),
                settings.digikey_sandbox,
            )
        )
    if "Mouser" in configured and settings.mouser_api_key:
        providers.append(MouserProvider(settings.mouser_api_key.get_secret_value()))
    if "element14" in configured and settings.element14_api_key:
        providers.append(
            Element14Provider(
                settings.element14_api_key.get_secret_value(), settings.element14_store
            )
        )
    return providers
