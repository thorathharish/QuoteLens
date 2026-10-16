"""Impact results (API-visible). Every number is a Fact with its provenance."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.domain.facts import Fact
from app.domain.models import LineImpact


class ImpactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecommendationKind(StrEnum):
    PRICE_BREAK_JUMP = "PRICE_BREAK_JUMP"


class ImpactRecommendation(ImpactModel):
    line_id: str
    kind: RecommendationKind
    message: str
    saving: Fact[Decimal]


class WaterfallStep(ImpactModel):
    label: str
    value: Fact[Decimal]


class ImpactTotals(ImpactModel):
    required_material: Fact[Decimal]
    scrap_cost: Fact[Decimal]
    excess_cost: Fact[Decimal]
    material: Fact[Decimal]
    adders: Fact[Decimal]
    grand_total: Fact[Decimal]
    per_unit: Fact[Decimal]


class ImpactResult(ImpactModel):
    volume: int
    currency: str
    totals: ImpactTotals
    waterfall: list[WaterfallStep]
    lines: list[LineImpact]
    recommendations: list[ImpactRecommendation]
    unpriced_line_ids: list[str]
