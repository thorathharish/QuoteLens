"""Domain models (LLD §3.2). Pure data, no I/O.

Money and quantities that may be fractional use `Decimal`. Values shown to users are
wrapped in `Fact` so their provenance travels with them.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.domain.enums import (
    ActionType,
    AlternativeSource,
    AlternativeStatus,
    ChatRole,
    CompareResult,
    DataMode,
    DemoRole,
    FitClass,
    IssueCode,
    JobStatus,
    JobType,
    Lifecycle,
    MatchStatus,
    NarrativeSource,
    ProjectStatus,
    QuoteStatus,
    RiskCategory,
    RiskStatus,
    Severity,
    SourceMode,
)
from app.domain.facts import Fact


def utcnow() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ── Project ──────────────────────────────────────────────────


class SourceFile(DomainModel):
    filename: str
    gcs_uri: str | None = None
    sha256: str
    sheet: str | None = None
    header_row: int | None = None


class ScrapTier(DomainModel):
    min_unit_price: Decimal
    scrap_pct: Decimal = Field(ge=0, le=1)


class ScrapPolicy(DomainModel):
    mode: str = Field(default="price_tier", pattern="^(price_tier|package|fixed)$")
    fixed_pct: Decimal | None = Field(default=None, ge=0, le=1)
    tiers: list[ScrapTier] = Field(
        default_factory=lambda: [
            ScrapTier(min_unit_price=Decimal("1.25"), scrap_pct=Decimal("0.01")),
            ScrapTier(min_unit_price=Decimal("0.25"), scrap_pct=Decimal("0.02")),
            ScrapTier(min_unit_price=Decimal("0"), scrap_pct=Decimal("0.05")),
        ]
    )


class Adders(DomainModel):
    assembly_per_unit: Decimal | None = Field(default=None, ge=0)
    nre: Decimal | None = Field(default=None, ge=0)
    overhead_pct: Decimal | None = Field(default=None, ge=0, le=1)
    margin_pct: Decimal | None = Field(default=None, ge=0, le=1)


class Assumptions(DomainModel):
    scrap_policy: ScrapPolicy = Field(default_factory=ScrapPolicy)
    fx_overrides: dict[str, Decimal] = {}
    adders: Adders = Field(default_factory=Adders)


class ProjectStats(DomainModel):
    lines: int = 0
    matched: int = 0
    risks_by_severity: dict[Severity, int] = {}
    open_blockers: int = 0
    spend_at_risk_pct: Decimal | None = None
    totals_by_volume: dict[str, Decimal] = {}


class Project(DomainModel):
    id: str
    name: str = Field(min_length=1, max_length=120)
    customer: str | None = None
    currency: str = Field(pattern="^[A-Z]{3}$")
    build_quantities: list[int] = Field(min_length=1, max_length=5)
    target_ship_date: date | None = None
    data_mode: DataMode = DataMode.CACHE_FIRST
    status: ProjectStatus = ProjectStatus.DRAFT
    source_file: SourceFile | None = None
    mapping: dict[str, str | None] = {}
    assumptions: Assumptions = Field(default_factory=Assumptions)
    stats: ProjectStats = Field(default_factory=ProjectStats)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ── BOM lines ────────────────────────────────────────────────


class Issue(DomainModel):
    code: IssueCode
    message: str
    field: str | None = None


class MatchResult(DomainModel):
    status: MatchStatus = MatchStatus.PENDING
    component_id: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    candidates: list[str] = []


class Override(DomainModel):
    old: JsonValue
    new: JsonValue
    reason: str
    by: DemoRole
    at: datetime = Field(default_factory=utcnow)


class BomLine(DomainModel):
    id: str
    line_no: int = Field(ge=1)
    cpn: str | None = None
    mpn_raw: str | None = None
    mpn: str | None = None
    manufacturer_raw: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    qty_per: Fact[Decimal]
    uom: str = "EA"
    refdes: list[str] = []
    dnp: bool = False
    bom_unit_price: Fact[Decimal] | None = None
    package: str | None = None
    validation: list[Issue] = []
    match: MatchResult = Field(default_factory=MatchResult)
    selected_offer_id: str | None = None
    substituted_from: str | None = None
    overrides: dict[str, Override] = {}
    version: int = 1


# ── Sourcing ─────────────────────────────────────────────────


class PriceBreak(DomainModel):
    qty: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0)


class Offer(DomainModel):
    id: str
    line_id: str
    distributor: str
    sku: str
    mpn: str
    manufacturer: str
    authorized: bool = True
    stock: int | None = Field(default=None, ge=0)
    moq: int | None = Field(default=None, ge=1)
    order_multiple: int | None = Field(default=None, ge=1)
    packaging: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    lifecycle: Lifecycle = Lifecycle.UNKNOWN
    price_breaks: list[PriceBreak] = []
    currency: str = Field(pattern="^[A-Z]{3}$")
    evidence_id: str
    mode: SourceMode
    fetched_at: datetime


class Component(DomainModel):
    id: str
    mpn: str
    manufacturer: str
    category: str | None = None
    description: str | None = None
    params: dict[str, JsonValue] = {}
    lifecycle: Lifecycle = Lifecycle.UNKNOWN
    ltb_date: date | None = None
    datasheet_url: str | None = None


# ── Risk ─────────────────────────────────────────────────────


class Action(DomainModel):
    type: ActionType
    label: str


class Risk(DomainModel):
    id: str
    line_id: str | None = None
    rule_id: str
    category: RiskCategory
    severity: Severity
    title: str
    why: str
    metrics: dict[str, JsonValue] = {}
    evidence_ids: list[str] = Field(min_length=1)
    suggested_actions: list[Action] = []
    status: RiskStatus = RiskStatus.OPEN
    resolution_note: str | None = None
    narrative_source: NarrativeSource = NarrativeSource.TEMPLATE
    cost_exposure: Fact[Decimal] | None = None


# ── Manufacturing impact ─────────────────────────────────────


class CalcStep(DomainModel):
    label: str
    formula: str
    inputs: dict[str, JsonValue] = {}
    output: Fact[Decimal]


class LineImpact(DomainModel):
    line_id: str
    volume: int = Field(ge=1)
    required: Fact[Decimal]
    scrap_pct: Fact[Decimal]
    gross: Fact[Decimal]
    net_need: Fact[Decimal]
    buy_qty: Fact[Decimal]
    excess_qty: Fact[Decimal]
    shortage_qty: Fact[Decimal]
    unit_price: Fact[Decimal]
    extended: Fact[Decimal]
    excess_cost: Fact[Decimal]
    per_unit_cost: Fact[Decimal]
    contribution_pct: Fact[Decimal]
    trace: list[CalcStep] = []


# ── Alternatives ─────────────────────────────────────────────


class AttrCompare(DomainModel):
    attribute: str
    original: str | None = None
    candidate: str | None = None
    critical: bool = False
    result: CompareResult


class Alternative(DomainModel):
    id: str
    line_id: str
    candidate_mpn: str
    manufacturer: str
    source: AlternativeSource
    fit_class: FitClass
    comparison: list[AttrCompare] = []
    offers_summary: dict[str, JsonValue] = {}
    delta_cost: Fact[Decimal] | None = None
    delta_lead_days: Fact[Decimal] | None = None
    explanation: str = ""
    evidence_ids: list[str] = []
    status: AlternativeStatus = AlternativeStatus.PROPOSED
    decided_by: DemoRole | None = None
    note: str | None = None


# ── Quotation ────────────────────────────────────────────────


class VolumeQuote(DomainModel):
    volume: int = Field(ge=1)
    material: Fact[Decimal]
    adders: Fact[Decimal]
    total: Fact[Decimal]
    per_unit: Fact[Decimal]


class Readiness(DomainModel):
    ready: bool
    open_blockers: list[str] = []
    waived: list[str] = []


def quote_version_id(version: int) -> str:
    """Zero-padded so lexical order equals version order."""
    return f"v{version:04d}"


class QuoteVersion(DomainModel):
    id: str
    version: int = Field(ge=1)
    status: QuoteStatus = QuoteStatus.DRAFT
    created_at: datetime = Field(default_factory=utcnow)
    finalized_at: datetime | None = None
    note: str | None = None
    currency: str
    volumes: list[VolumeQuote]
    assumptions: Assumptions
    readiness: Readiness
    line_snapshot_ref: str | None = None


# ── Jobs, audit, chat ────────────────────────────────────────


class JobError(DomainModel):
    code: str
    message: str


class Job(DomainModel):
    id: str
    project_id: str
    type: JobType
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    warnings: list[str] = []
    error: JobError | None = None
    payload: dict[str, JsonValue] = {}
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AuditEvent(DomainModel):
    id: str
    actor_role: DemoRole
    action: str
    target: str
    before: dict[str, JsonValue] = {}
    after: dict[str, JsonValue] = {}
    reason: str | None = None
    at: datetime = Field(default_factory=utcnow)


class Citation(DomainModel):
    evidence_id: str
    label: str


class ToolCall(DomainModel):
    name: str
    args: dict[str, JsonValue] = {}


class ChatMessage(DomainModel):
    id: str
    role: ChatRole
    content: str
    citations: list[Citation] = []
    tool_calls: list[ToolCall] = []
    grounded: bool | None = None
    created_at: datetime = Field(default_factory=utcnow)
