"""Request/response DTOs for /api/v1. Domain models are reused for responses where their
shape is already the public contract; internal fields are excluded explicitly."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.catalog.rows import CatalogComponent, CatalogOffer
from app.domain.enums import BomField, DataMode, MappingMethod, ProjectStatus, RiskStatus
from app.domain.facts import Evidence, Fact
from app.domain.models import (
    Alternative,
    Assumptions,
    BomLine,
    BomUpload,
    Component,
    LineImpact,
    Offer,
    OfferRecommendation,
    Project,
    Risk,
)
from app.impact.models import ImpactResult
from app.risk.engine import RiskSummary


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    customer: str | None = Field(default=None, max_length=120)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    build_quantities: list[Annotated[int, Field(ge=1, le=1_000_000)]] = Field(
        min_length=1, max_length=5
    )
    target_ship_date: date | None = None
    data_mode: DataMode = DataMode.CACHE_FIRST


class ProjectPage(ApiModel):
    items: list[Project]
    next_cursor: str | None = None


class MappingColumn(ApiModel):
    column_index: int
    header: str
    field: BomField | None
    confidence: float
    method: MappingMethod
    reason: str | None = None


class UploadPreview(ApiModel):
    upload_id: str
    filename: str
    sheets: list[str]
    selected_sheet: str
    header_row: int = Field(description="1-based row number of the detected header")
    data_rows: int
    proposed_mapping: list[MappingColumn]
    preview_rows: list[list[str | None]]
    unmapped: list[str]
    warnings: list[str]

    @classmethod
    def of(cls, upload: BomUpload) -> "UploadPreview":
        return cls(
            upload_id=upload.id,
            filename=upload.filename,
            sheets=upload.sheets,
            selected_sheet=upload.selected_sheet,
            header_row=upload.header_row,
            data_rows=upload.data_rows,
            proposed_mapping=[MappingColumn.model_validate(m.model_dump()) for m in upload.mapping],
            preview_rows=upload.preview_rows,
            unmapped=[m.header for m in upload.mapping if m.field is None and m.header],
            warnings=upload.warnings,
        )


class MappingChoiceIn(ApiModel):
    column_index: int = Field(ge=0)
    field: BomField | None


class MappingConfirm(ApiModel):
    upload_id: str
    mapping: list[MappingChoiceIn] = Field(
        description="Overrides by column; columns not listed keep the proposed field"
    )
    sheet: str | None = None
    header_row: int | None = Field(default=None, ge=1)


class JobAccepted(ApiModel):
    job_id: str


class LinePage(ApiModel):
    items: list[BomLine]
    issue_counts: dict[str, int]
    next_cursor: str | None = None


class AnalysisRequest(ApiModel):
    line_ids: list[str] | None = Field(default=None, description="Only these lines; all if omitted")


class LineDetail(ApiModel):
    line: BomLine
    component: Component | None
    offers: list[Offer]
    selected_offer: Offer | None
    recommendation: OfferRecommendation | None
    evidence: dict[str, Evidence]
    risks: list[Risk] = Field(default=[], description="Populated from Phase 4")
    impact_by_volume: list[LineImpact] = Field(default=[], description="Populated from Phase 4")
    alternatives: list[Alternative] = Field(default=[], description="Populated from Phase 5")


class OffersResponse(ApiModel):
    offers: list[Offer]
    recommendation: OfferRecommendation | None


class MpnUpdate(ApiModel):
    mpn: str = Field(min_length=1, max_length=64)
    manufacturer: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=500)


class OfferSelection(ApiModel):
    offer_id: str
    reason: str = Field(min_length=3, max_length=500)


class ComponentLookup(ApiModel):
    mpn: str
    component: CatalogComponent | None
    offers: list[CatalogOffer]
    suggestions: list[str]
    warnings: list[str]


# ── Phase 4: overview, impact, risks ─────────────────────────


class VolumeTotal(ApiModel):
    volume: int
    material: Fact[Decimal]
    total: Fact[Decimal]
    per_unit: Fact[Decimal]


class NextAction(ApiModel):
    label: str
    risk_id: str | None = None
    line_id: str | None = None


class Overview(ApiModel):
    project_id: str
    status: ProjectStatus
    data_mode: DataMode
    currency: str
    lines: int
    matched: int
    unpriced_lines: int
    totals_by_volume: list[VolumeTotal]
    risks: RiskSummary
    next_actions: list[NextAction]


class RiskList(ApiModel):
    summary: RiskSummary
    items: list[Risk]


class RiskDetail(ApiModel):
    risk: Risk
    evidence: dict[str, Evidence]


class RiskReview(ApiModel):
    status: RiskStatus
    note: str | None = Field(default=None, max_length=1000)


class LineOverrideIn(ApiModel):
    line_id: str
    scrap_pct: Decimal | None = Field(default=None, ge=0, le=1)
    offer_id: str | None = None
    qty_per: Decimal | None = Field(default=None, gt=0)
    on_hand: int | None = Field(default=None, ge=0)


class SimulationRequest(ApiModel):
    volume: int = Field(ge=1, le=10_000_000)
    overrides: list[LineOverrideIn] = Field(default=[], max_length=500)


class SimulationResult(ApiModel):
    baseline: ImpactResult
    simulated: ImpactResult
    delta: Fact[Decimal]


AssumptionsBody = Assumptions


# ── Phase 5: alternatives ────────────────────────────────────


class AlternativeSearch(ApiModel):
    reason: str | None = Field(default=None, max_length=500)


class AlternativeDecision(ApiModel):
    decision: Literal["APPROVE", "REJECT"]
    note: str = Field(min_length=3, max_length=1000)


class AlternativeList(ApiModel):
    items: list[Alternative]


class DecisionResult(ApiModel):
    alternative: Alternative
    line: BomLine
