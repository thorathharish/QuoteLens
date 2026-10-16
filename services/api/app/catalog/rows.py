"""Row models for the BigQuery catalog tables (LLD §3.4).

These are the single definition of the catalog shape. The seed generator, the loader, the
BigQuery JSON schemas (checked by a parity test) and the catalog provider all use them.
"""

from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.domain.enums import Lifecycle, SourceMode
from app.domain.mpn import normalize_mpn


class CatalogRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogPriceBreak(CatalogRow):
    qty: int = Field(ge=1)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=6)


class CatalogComponent(CatalogRow):
    """`catalog.components`: one row per manufacturer part."""

    mpn_norm: str = Field(min_length=1)
    mpn: str = Field(min_length=1)
    manufacturer: str = Field(min_length=1)
    category: str
    description: str
    package: str | None = None
    params: dict[str, JsonValue] = {}
    lifecycle: Lifecycle = Lifecycle.UNKNOWN
    ltb_date: date | None = None
    rohs: bool | None = None
    datasheet_url: str | None = None
    source: str
    snapshot_date: date

    @model_validator(mode="after")
    def _ltb_requires_ending_lifecycle(self) -> Self:
        if normalize_mpn(self.mpn) != self.mpn_norm:
            raise ValueError(f"{self.mpn}: mpn_norm must equal normalize_mpn(mpn)")
        if self.ltb_date is not None and self.lifecycle is Lifecycle.ACTIVE:
            raise ValueError(f"{self.mpn}: ACTIVE parts must not have an LTB date")
        return self


class CatalogOffer(CatalogRow):
    """`catalog.offers_cache`: one row per (part, distributor SKU) snapshot."""

    mpn_norm: str = Field(min_length=1)
    distributor: str
    sku: str
    manufacturer: str
    stock: int | None = Field(default=None, ge=0)
    moq: int = Field(ge=1)
    mult: int = Field(ge=1)
    lead_days: int | None = Field(default=None, ge=0)
    packaging: str | None = None
    price_breaks: list[CatalogPriceBreak] = Field(min_length=1)
    currency: str = Field(pattern="^[A-Z]{3}$")
    authorized: bool = True
    lifecycle: Lifecycle = Lifecycle.UNKNOWN
    fetched_at: datetime
    mode: SourceMode
    source_url: str | None = None

    @field_validator("price_breaks")
    @classmethod
    def _breaks_ascending_and_non_increasing(
        cls, breaks: list[CatalogPriceBreak]
    ) -> list[CatalogPriceBreak]:
        quantities = [b.qty for b in breaks]
        if quantities != sorted(set(quantities)):
            raise ValueError("price break quantities must be strictly ascending")
        prices = [b.price for b in breaks]
        if any(later > earlier for earlier, later in pairwise(prices)):
            raise ValueError("unit price must not increase at higher quantity breaks")
        return breaks

    @model_validator(mode="after")
    def _key_is_normalized(self) -> Self:
        if normalize_mpn(self.mpn_norm) != self.mpn_norm:
            raise ValueError(f"mpn_norm '{self.mpn_norm}' is not normalized")
        return self


class CatalogCrossRef(CatalogRow):
    """`catalog.crossrefs`: a known alternate for a part."""

    mpn_norm: str
    alt_mpn_norm: str
    alt_mpn: str
    alt_manufacturer: str
    relation: str = Field(pattern="^(FFF|FUNCTIONAL|UPGRADE)$")
    source: str
    note: str | None = None
