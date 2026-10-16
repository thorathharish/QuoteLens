"""The risk rule catalog (LLD §3.5). Each rule is a pure function of one line's context and
returns an explained Risk (why + metrics + evidence + suggested actions) or None.

Explanations are deterministic templates filled from the metrics, so they can never state
a number the data does not contain.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import median

from app.domain.enums import ActionType as A
from app.domain.enums import IssueCode, Lifecycle, MatchStatus, SourceMode
from app.domain.enums import RiskCategory as C
from app.domain.enums import Severity as S  # noqa: N817 - compact rule table
from app.domain.models import Risk
from app.pricing.fx import convert
from app.pricing.price_breaks import unit_price_at
from app.risk.context import DEFAULT_HORIZON_DAYS, RiskContext, fmt

Rule = Callable[[RiskContext], Risk | None]

PRICE_SPREAD_FACTOR = Decimal("1.4")
TARGET_DEVIATION = Decimal("0.25")
EXCESS_SHARE = Decimal("0.20")
CONCENTRATION_SHARE = Decimal("0.15")
STALE_DAYS = 7
LTB_WARNING_DAYS = 90


def _has(ctx: RiskContext, code: IssueCode) -> bool:
    return any(issue.code is code for issue in ctx.line.validation)


def _issue_message(ctx: RiskContext, *codes: IssueCode) -> str:
    return next((i.message for i in ctx.line.validation if i.code in codes), "")


# ── Data quality ─────────────────────────────────────────────


def d01_missing_mpn(ctx: RiskContext) -> Risk | None:
    if ctx.line.mpn is not None:
        return None
    return ctx.risk(
        "D01",
        C.DATA,
        S.BLOCKER,
        "Missing manufacturer part number",
        f"{ctx.label} has no manufacturer part number, so it cannot be sourced or priced. "
        "The quote cannot be finalized until a part number is provided.",
        evidence=ctx.bom_evidence(),
        metrics={"description": ctx.line.description},
        actions=[(A.EDIT_LINE, "Add the MPN"), (A.CONFIRM_WITH_CUSTOMER, "Ask the customer")],
    )


def d02_missing_manufacturer(ctx: RiskContext) -> Risk | None:
    if ctx.line.mpn is None or not _has(ctx, IssueCode.MISSING_MFR):
        return None
    catalog = ctx.component.manufacturer if ctx.component else None
    why = f"The manufacturer is empty for {ctx.line.mpn}. " + (
        f"The catalog lists it as made by {catalog}; confirm that is the intended maker."
        if catalog
        else "The maker cannot be confirmed from the data."
    )
    return ctx.risk(
        "D02",
        C.DATA,
        S.MEDIUM,
        "Manufacturer not specified",
        why,
        evidence=[*ctx.bom_evidence(), (ctx.component.evidence_id or "") if ctx.component else ""],
        metrics={"catalog_manufacturer": catalog},
        actions=[(A.EDIT_LINE, f"Set manufacturer{f' to {catalog}' if catalog else ''}")],
    )


def d03_not_found(ctx: RiskContext) -> Risk | None:
    if ctx.line.mpn is None or ctx.line.dnp or ctx.line.match.status is not MatchStatus.NOT_FOUND:
        return None
    candidates = ctx.line.match.candidates
    why = f"{ctx.line.mpn} was not found in any data source for this project."
    if candidates:
        why += f" Closest known part numbers: {', '.join(candidates)}. A typo is likely."
    return ctx.risk(
        "D03",
        C.DATA,
        S.HIGH,
        "Part number not found",
        why,
        evidence=ctx.bom_evidence(),
        metrics={"mpn": ctx.line.mpn, "candidates": list(candidates)},
        actions=[
            (A.EDIT_LINE, f"Use {candidates[0]}" if candidates else "Correct the MPN"),
            (A.CONFIRM_WITH_CUSTOMER, "Confirm the part with the customer"),
        ],
    )


def d04_quantity_invalid(ctx: RiskContext) -> Risk | None:
    codes = (IssueCode.QTY_INVALID, IssueCode.UOM_CONFLICT)
    if not any(_has(ctx, c) for c in codes):
        return None
    detail = _issue_message(ctx, *codes)
    return ctx.risk(
        "D04",
        C.DATA,
        S.BLOCKER,
        "Invalid quantity or unit",
        f"The quantity for {ctx.label} is unusable ({detail}), so required quantity and cost "
        "cannot be calculated.",
        evidence=ctx.bom_evidence(),
        metrics={"detail": detail},
        actions=[
            (A.EDIT_LINE, "Correct the quantity"),
            (A.CONFIRM_WITH_CUSTOMER, "Ask the customer"),
        ],
    )


def d05_refdes_mismatch(ctx: RiskContext) -> Risk | None:
    if not _has(ctx, IssueCode.REFDES_QTY_MISMATCH):
        return None
    count, qty = len(ctx.line.refdes), ctx.line.qty_per.value
    return ctx.risk(
        "D05",
        C.QUANTITY,
        S.MEDIUM,
        "Designators do not match quantity",
        f"{count} reference designators are listed but the quantity is {fmt(qty)}. One of them "
        "is wrong; the quote currently uses the quantity column.",
        evidence=ctx.bom_evidence(),
        metrics={"designators": count, "qty_per": fmt(qty)},
        actions=[(A.EDIT_LINE, "Fix quantity or designators")],
    )


def d06_manufacturer_mismatch(ctx: RiskContext) -> Risk | None:
    match = ctx.line.match
    if match.status is not MatchStatus.MATCHED or match.confidence >= 1 or ctx.component is None:
        return None
    return ctx.risk(
        "D06",
        C.DATA,
        S.MEDIUM,
        "Manufacturer differs from catalog",
        f"The BOM lists {ctx.line.manufacturer} but {ctx.line.mpn} is made by "
        f"{ctx.component.manufacturer} according to the catalog.",
        evidence=[*ctx.bom_evidence(), ctx.component.evidence_id or ""],
        metrics={"bom": ctx.line.manufacturer, "catalog": ctx.component.manufacturer},
        actions=[(A.CONFIRM_WITH_CUSTOMER, "Confirm the intended manufacturer")],
    )


def d07_ambiguous(ctx: RiskContext) -> Risk | None:
    if ctx.line.match.status is not MatchStatus.AMBIGUOUS:
        return None
    return ctx.risk(
        "D07",
        C.DATA,
        S.HIGH,
        "Ambiguous part match",
        f"{ctx.line.mpn} matches several parts: {', '.join(ctx.line.match.candidates)}.",
        evidence=ctx.bom_evidence(),
        metrics={"candidates": list(ctx.line.match.candidates)},
        actions=[(A.EDIT_LINE, "Choose the intended part")],
    )


# ── Lifecycle ────────────────────────────────────────────────


def l01_end_of_life(ctx: RiskContext) -> Risk | None:
    component = ctx.component
    if component is None or component.lifecycle not in (Lifecycle.EOL, Lifecycle.OBSOLETE):
        return None
    need = ctx.need
    authorized_stock = sum(o.stock or 0 for o in ctx.authorized)
    broker_stock = sum(o.stock or 0 for o in ctx.offers if not o.authorized)
    short = need is None or authorized_stock < need
    why = f"{ctx.line.mpn} is {component.lifecycle.value.lower()} per the catalog"
    if component.ltb_date:
        why += f" (last-time-buy date {component.ltb_date.isoformat()})"
    why += (
        f". Authorized distributors hold {fmt(authorized_stock)} units against "
        f"{fmt(need)} needed for {fmt(ctx.volume)} boards"
    )
    if broker_stock:
        why += f"; {fmt(broker_stock)} units exist only at unauthorized brokers (counterfeit risk)"
    why += "."
    return ctx.risk(
        "L01",
        C.LIFECYCLE,
        S.BLOCKER if short else S.HIGH,
        f"Part is {component.lifecycle.value}",
        why,
        evidence=[component.evidence_id or "", *(o.evidence_id for o in ctx.offers)],
        metrics={
            "lifecycle": component.lifecycle.value,
            "authorized_stock": authorized_stock,
            "broker_stock": broker_stock,
            "need": fmt(need),
            "ltb_date": component.ltb_date.isoformat() if component.ltb_date else None,
        },
        actions=[
            (A.SEARCH_ALTERNATIVES, "Find a drop-in alternate"),
            (A.CONFIRM_WITH_CUSTOMER, "Agree a replacement with the customer"),
        ],
    )


def l02_not_recommended(ctx: RiskContext) -> Risk | None:
    component = ctx.component
    if component is None:
        return None
    target = ctx.project.target_ship_date
    ltb_soon = (
        component.ltb_date is not None
        and target is not None
        and component.ltb_date < target + timedelta(days=LTB_WARNING_DAYS)
    )
    flagged = component.lifecycle in (Lifecycle.NRND, Lifecycle.LAST_TIME_BUY)
    if (not flagged and not ltb_soon) or component.lifecycle in (Lifecycle.EOL, Lifecycle.OBSOLETE):
        return None
    label = {"NRND": "not recommended for new designs", "LAST_TIME_BUY": "in last-time-buy"}.get(
        component.lifecycle.value, component.lifecycle.value.lower()
    )
    why = f"{ctx.line.mpn} is {label} per the catalog"
    if component.ltb_date:
        why += f", with a last-time-buy date of {component.ltb_date.isoformat()}"
    why += ". Supply may end during the product's life."
    return ctx.risk(
        "L02",
        C.LIFECYCLE,
        S.HIGH,
        "Part nearing end of life",
        why,
        evidence=[component.evidence_id or ""],
        metrics={
            "lifecycle": component.lifecycle.value,
            "ltb_date": component.ltb_date.isoformat() if component.ltb_date else None,
        },
        actions=[
            (A.SEARCH_ALTERNATIVES, "Evaluate the successor part"),
            (A.ACCEPT_RISK, "Accept with a lifetime-buy plan"),
        ],
    )


# ── Supply ───────────────────────────────────────────────────


def s01_insufficient_stock(ctx: RiskContext) -> Risk | None:
    need = ctx.need
    if ctx.line.match.status is not MatchStatus.MATCHED or need is None or not ctx.offers:
        return None
    stock = sum(o.stock or 0 for o in ctx.authorized)
    if stock >= need:
        return None
    return ctx.risk(
        "S01",
        C.SUPPLY,
        S.HIGH,
        "Not enough authorized stock",
        f"Authorized distributors hold {fmt(stock)} units in total, but {fmt(need)} are needed "
        f"for {fmt(ctx.volume)} boards (short by {fmt(need - stock)}).",
        evidence=[o.evidence_id for o in ctx.authorized] or [o.evidence_id for o in ctx.offers],
        metrics={"authorized_stock": stock, "need": fmt(need), "shortfall": fmt(need - stock)},
        actions=[
            (A.SEARCH_ALTERNATIVES, "Find an alternate in stock"),
            (A.CONFIRM_WITH_CUSTOMER, "Agree a later delivery"),
        ],
    )


def s02_single_source(ctx: RiskContext) -> Risk | None:
    distributors = {o.distributor for o in ctx.authorized}
    if len(distributors) != 1:
        return None
    (only,) = distributors
    return ctx.risk(
        "S02",
        C.SUPPLY,
        S.MEDIUM,
        "Single authorized source",
        f"Only {only} lists {ctx.line.mpn} as an authorized source; a disruption there has no "
        "fallback.",
        evidence=[o.evidence_id for o in ctx.authorized],
        metrics={"distributor": only},
        actions=[
            (A.SEARCH_ALTERNATIVES, "Qualify a second source"),
            (A.ACCEPT_RISK, "Accept and buy ahead"),
        ],
    )


def s03_lead_time(ctx: RiskContext) -> Risk | None:
    offer, impact = ctx.selected, ctx.impact
    if offer is None or impact is None or offer.lead_time_days is None:
        return None
    shortage = impact.shortage_qty.value
    if shortage is None or shortage <= 0:
        return None
    target = ctx.project.target_ship_date
    horizon = (target - ctx.today).days if target else DEFAULT_HORIZON_DAYS
    if offer.lead_time_days <= horizon:
        return None
    deadline = (
        f"the target ship date {target.isoformat()} ({horizon} days away)"
        if target
        else f"the assumed {DEFAULT_HORIZON_DAYS}-day planning horizon (no target date set)"
    )
    return ctx.risk(
        "S03",
        C.SUPPLY,
        S.HIGH,
        "Lead time exceeds the schedule",
        f"{offer.distributor} has {fmt(offer.stock)} in stock against "
        f"{fmt(impact.buy_qty.value)} to buy; the remaining {fmt(shortage)} ship in "
        f"{offer.lead_time_days} days, after {deadline}.",
        evidence=[offer.evidence_id],
        metrics={
            "lead_days": offer.lead_time_days,
            "horizon_days": horizon,
            "shortage": fmt(shortage),
            "target_ship_date": target.isoformat() if target else None,
        },
        actions=[
            (A.SEARCH_ALTERNATIVES, "Find an alternate with stock"),
            (A.CONFIRM_WITH_CUSTOMER, "Negotiate the delivery date"),
        ],
    )


def s04_no_authorized_source(ctx: RiskContext) -> Risk | None:
    if not ctx.offers or ctx.authorized:
        return None
    return ctx.risk(
        "S04",
        C.SUPPLY,
        S.HIGH,
        "No authorized source",
        f"Only unauthorized (broker) offers exist for {ctx.line.mpn}; parts would have no "
        "traceability to the manufacturer.",
        evidence=[o.evidence_id for o in ctx.offers],
        metrics={"offers": len(ctx.offers)},
        actions=[(A.SEARCH_ALTERNATIVES, "Find an alternate with authorized supply")],
    )


# ── Price ────────────────────────────────────────────────────


def _price_at(ctx: RiskContext, qty: int) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for offer in ctx.authorized:
        native = unit_price_at(offer.price_breaks, max(qty, offer.moq or 1))
        converted = (
            convert(native, offer.currency, ctx.currency, ctx.project.assumptions.fx_overrides)
            if native is not None
            else None
        )
        if converted is not None:
            prices[offer.distributor] = min(converted, prices.get(offer.distributor, converted))
    return prices


def p01_price_spread(ctx: RiskContext) -> Risk | None:
    need = ctx.need
    if need is None:
        return None
    prices = _price_at(ctx, int(need))
    if len(prices) < 2:
        return None
    mid = Decimal(median(prices.values()))
    top_dist, top = max(prices.items(), key=lambda kv: kv[1])
    if not mid or top <= mid * PRICE_SPREAD_FACTOR:
        return None
    ratio = (top / mid).quantize(Decimal("0.1"))
    return ctx.risk(
        "P01",
        C.PRICE,
        S.MEDIUM,
        "Large price spread between distributors",
        f"Unit prices at {fmt(need)} units range from {ctx.money(min(prices.values()))} to "
        f"{ctx.money(top)}; {top_dist} is {ratio}× the median ({ctx.money(mid)}).",
        evidence=[o.evidence_id for o in ctx.authorized],
        metrics={
            "min": str(min(prices.values())),
            "max": str(top),
            "median": str(mid),
            "outlier": top_dist,
            "ratio": str(ratio),
        },
        actions=[(A.SELECT_OFFER, f"Avoid {top_dist} for this part")],
    )


def p02_target_price(ctx: RiskContext) -> Risk | None:
    target = ctx.line.bom_unit_price
    impact = ctx.impact
    if target is None or target.value is None or impact is None or impact.unit_price.value is None:
        return None
    market = impact.unit_price.value
    if target.value >= market * (1 - TARGET_DEVIATION):
        return None  # at or above market (minus tolerance) is not a quoting risk
    gap = ((market - target.value) / market * 100).quantize(Decimal("1"))
    seller = ctx.selected.distributor if ctx.selected else "market"
    return ctx.risk(
        "P02",
        C.PRICE,
        S.MEDIUM,
        "Customer target below market price",
        f"The customer's target price ({ctx.money(target.value)}) is {gap}% below the selected "
        f"market price ({ctx.money(market)} at {seller}). "
        "Quoting at market will exceed the target.",
        evidence=[*target.evidence_ids, *impact.unit_price.evidence_ids],
        metrics={"target": str(target.value), "market": str(market), "gap_pct": str(gap)},
        actions=[
            (A.CONFIRM_WITH_CUSTOMER, "Discuss the target price"),
            (A.SEARCH_ALTERNATIVES, "Look for a cheaper alternate"),
        ],
    )


def p03_moq_excess(ctx: RiskContext) -> Risk | None:
    impact, offer = ctx.impact, ctx.selected
    if impact is None or offer is None:
        return None
    excess, extended = impact.excess_cost.value, impact.extended.value
    if not excess or not extended or excess <= extended * EXCESS_SHARE:
        return None
    share = (excess / extended * 100).quantize(Decimal("1"))
    return ctx.risk(
        "P03",
        C.PRICE,
        S.MEDIUM,
        "MOQ forces costly excess",
        f"Buying {ctx.line.mpn} at {offer.distributor} requires {fmt(impact.buy_qty.value)} units "
        f"(MOQ {fmt(offer.moq)}, multiples of {fmt(offer.order_multiple)}) but only "
        f"{fmt(impact.net_need.value)} are needed: {ctx.money(excess)} of excess, {share}% of "
        "the line's cost.",
        evidence=[offer.evidence_id],
        metrics={
            "excess_cost": str(excess),
            "line_cost": str(extended),
            "share_pct": str(share),
            "moq": offer.moq,
            "multiple": offer.order_multiple,
        },
        actions=[
            (A.SELECT_OFFER, "Choose a cut-tape offer"),
            (A.ACCEPT_RISK, "Accept and keep the excess as stock"),
        ],
    )


def p04_stale_price(ctx: RiskContext) -> Risk | None:
    offer = ctx.selected
    if offer is None or offer.mode is SourceMode.DEMO_SNAPSHOT:
        return None  # snapshot data is disclosed globally, not per line
    age = (datetime.now(UTC) - offer.fetched_at).days
    if age <= STALE_DAYS:
        return None
    return ctx.risk(
        "P04",
        C.PRICE,
        S.LOW,
        "Price data is stale",
        f"The {offer.distributor} price was fetched {age} days ago; refresh before finalizing.",
        evidence=[offer.evidence_id],
        metrics={"age_days": age},
        actions=[(A.SELECT_OFFER, "Refresh live prices")],
    )


def p05_no_price(ctx: RiskContext) -> Risk | None:
    component = ctx.component
    if (
        ctx.line.match.status is not MatchStatus.MATCHED
        or not ctx.authorized
        or ctx.selected
        or not ctx.line.qty_per.is_available  # D04 already explains an unusable quantity
        or (component and component.lifecycle in (Lifecycle.EOL, Lifecycle.OBSOLETE))
    ):
        return None
    reasons = ctx.line.recommendation.reasons if ctx.line.recommendation else []
    return ctx.risk(
        "P05",
        C.PRICE,
        S.HIGH,
        "No price for the required quantity",
        f"{ctx.line.mpn} is listed by distributors, but none can be priced for this order: "
        + "; ".join(reasons[1:] or reasons or ["no eligible offer"])
        + ".",
        evidence=[o.evidence_id for o in ctx.authorized],
        metrics={"reasons": list(reasons)},
        actions=[(A.CONFIRM_WITH_CUSTOMER, "Request a quote from the distributor")],
    )


# ── Quantity / concentration ─────────────────────────────────


def q01_concentration(ctx: RiskContext) -> Risk | None:
    impact = ctx.impact
    if impact is None or impact.extended.value is None or not ctx.material_total:
        return None
    share = impact.extended.value / ctx.material_total
    if share <= CONCENTRATION_SHARE:
        return None
    pct = (share * 100).quantize(Decimal("1"))
    return ctx.risk(
        "Q01",
        C.QUANTITY,
        S.LOW,
        "Large share of BOM cost",
        f"This line is {pct}% of the material cost at {fmt(ctx.volume)} boards "
        f"({ctx.money(impact.extended.value)} of {ctx.money(ctx.material_total)}); price or supply "
        "changes here move the whole quote.",
        evidence=list(impact.extended.evidence_ids),
        metrics={"share_pct": str(pct), "line_cost": str(impact.extended.value)},
        actions=[(A.SEARCH_ALTERNATIVES, "Check for a cheaper equivalent")],
    )


RULES: tuple[Rule, ...] = (
    d01_missing_mpn,
    d02_missing_manufacturer,
    d03_not_found,
    d04_quantity_invalid,
    d05_refdes_mismatch,
    d06_manufacturer_mismatch,
    d07_ambiguous,
    l01_end_of_life,
    l02_not_recommended,
    s01_insufficient_stock,
    s02_single_source,
    s03_lead_time,
    s04_no_authorized_source,
    p01_price_spread,
    p02_target_price,
    p03_moq_excess,
    p04_stale_price,
    p05_no_price,
    q01_concentration,
)
