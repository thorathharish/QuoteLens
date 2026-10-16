from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.enums import (
    Lifecycle,
    MatchStatus,
    RiskStatus,
    Severity,
    SourceMode,
)
from app.domain.facts import actual
from app.domain.models import (
    BomLine,
    Component,
    MatchResult,
    Offer,
    PriceBreak,
    Project,
)
from app.impact.engine import compute_line
from app.risk.context import RiskContext
from app.risk.engine import carry_decisions, summarize
from app.risk.rules import (
    l02_not_recommended,
    p02_target_price,
    p04_stale_price,
    s03_lead_time,
    s04_no_authorized_source,
)

TODAY = date(2026, 10, 17)
NOW = datetime(2026, 10, 17, tzinfo=UTC)


def _project(target: date | None = None) -> Project:
    return Project(
        id="prj", name="P", currency="USD", build_quantities=[100], target_ship_date=target
    )


def _line(**kw: object) -> BomLine:
    base = {
        "id": "ln_1",
        "line_no": 1,
        "mpn": "P1",
        "qty_per": actual(Decimal(1), "ev_bom"),
        "match": MatchResult(status=MatchStatus.MATCHED, component_id="P1", confidence=1.0),
        "selected_offer_id": "off_1",
    }
    return BomLine.model_validate({**base, **kw})


def _offer(**kw: object) -> Offer:
    base = {
        "id": "off_1",
        "line_id": "ln_1",
        "distributor": "DigiKey",
        "sku": "S",
        "mpn": "P1",
        "manufacturer": "M",
        "stock": 10_000,
        "moq": 1,
        "order_multiple": 1,
        "lead_time_days": 60,
        "currency": "USD",
        "evidence_id": "ev_off",
        "mode": SourceMode.DEMO_SNAPSHOT,
        "fetched_at": NOW,
        "price_breaks": [PriceBreak(qty=1, unit_price=Decimal("1.00"))],
    }
    return Offer.model_validate({**base, **kw})


def _ctx(
    line: BomLine | None = None,
    offers: list[Offer] | None = None,
    *,
    component: Component | None = None,
    project: Project | None = None,
) -> RiskContext:
    line = line or _line()
    offers = offers if offers is not None else [_offer()]
    project = project or _project()
    selected = next((o for o in offers if o.id == line.selected_offer_id), None)
    impact = (
        compute_line(line, selected, 100, project.assumptions, "USD").impact if selected else None
    )
    return RiskContext(
        project=project,
        line=line,
        component=component,
        offers=offers,
        selected=selected,
        impact=impact,
        material_total=Decimal(1000),
        today=TODAY,
    )


def test_target_price_only_flags_targets_below_market() -> None:
    below = _line(bom_unit_price=actual(Decimal("0.70"), "ev_bom"))
    above = _line(bom_unit_price=actual(Decimal("1.20"), "ev_bom"))
    risk = p02_target_price(_ctx(below))
    assert risk is not None
    assert "30% below" in risk.why
    assert p02_target_price(_ctx(above)) is None


def test_lead_time_uses_target_date_or_an_explicit_default() -> None:
    short_stock = [_offer(stock=10, lead_time_days=70)]
    soon = _project(target=TODAY + timedelta(days=30))
    risk = s03_lead_time(_ctx(offers=short_stock, project=soon))
    assert risk is not None
    assert "30 days away" in risk.why
    # No target date: 70 days fits within the assumed 84-day horizon, and the text says so
    assert s03_lead_time(_ctx(offers=short_stock)) is None
    late = s03_lead_time(_ctx(offers=[_offer(stock=10, lead_time_days=120)]))
    assert late is not None
    assert "assumed 84-day planning horizon" in late.why
    # Stock covers the order: lead time is irrelevant
    assert s03_lead_time(_ctx(offers=[_offer(lead_time_days=200)], project=soon)) is None


def test_ltb_date_close_to_shipping_is_flagged() -> None:
    component = Component(
        id="P1",
        mpn="P1",
        manufacturer="M",
        lifecycle=Lifecycle.LAST_TIME_BUY,
        ltb_date=TODAY + timedelta(days=40),
        evidence_id="ev_cmp",
    )
    risk = l02_not_recommended(
        _ctx(component=component, project=_project(TODAY + timedelta(days=30)))
    )
    assert risk is not None
    assert risk.severity is Severity.HIGH
    assert risk.evidence_ids == ["ev_cmp"]


def test_broker_only_and_stale_prices() -> None:
    broker = [_offer(authorized=False)]
    assert s04_no_authorized_source(_ctx(offers=broker)) is not None
    assert s04_no_authorized_source(_ctx()) is None

    stale = [_offer(mode=SourceMode.CACHE, fetched_at=datetime.now(UTC) - timedelta(days=30))]
    assert p04_stale_price(_ctx(offers=stale)) is not None
    old_snapshot = [_offer(fetched_at=datetime.now(UTC) - timedelta(days=30))]
    assert p04_stale_price(_ctx(offers=old_snapshot)) is None  # snapshots are disclosed globally


def test_decisions_survive_reevaluation_and_drive_readiness() -> None:
    blocker = _ctx(_line(mpn=None, id="ln_x")).risk(
        "D01",
        __import__("app.domain.enums", fromlist=["RiskCategory"]).RiskCategory.DATA,
        Severity.BLOCKER,
        "t",
        "why",
        evidence=["ev"],
        metrics={},
        actions=[],
    )
    waived = blocker.model_copy(update={"status": RiskStatus.WAIVED, "resolution_note": "ok"})
    (carried,) = carry_decisions([blocker], [waived])
    assert carried.status is RiskStatus.WAIVED
    assert carried.resolution_note == "ok"

    open_summary = summarize([blocker], 2, {"ln_x": Decimal(50)}, Decimal(200))
    assert open_summary.open_blockers == 1
    assert not open_summary.ready
    assert open_summary.readiness_pct.value == Decimal("0.500")
    assert open_summary.spend_at_risk_pct.value == Decimal("0.250")
    assert summarize([carried], 2, {}, Decimal(200)).ready
