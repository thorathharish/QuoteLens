# Low-Level Design (LLD)

> QuoteLens · AI Builder Cup 2026 · Manufacturing track. Part of the design package; see [README](README.md).

## 3. Low-level design (LLD)

### 3.1 Repository layout
```
/apps/web                    Next.js 15 App Router, TS strict, Tailwind + shadcn/ui, TanStack Query/Table, zod
  app/(marketing)/page.tsx   landing + "Run guided demo"
  app/projects/[id]/...      upload, mapping, workspace tabs
  components/fact/           <FactValue/>, <ProvenanceBadge/>, <EvidenceDrawer/>
  components/copilot/        chat drawer (SSE), citation chips
  lib/api/                   generated types (openapi-typescript) + fetch client
/services/api                FastAPI (api + worker entrypoints), uv, ruff, mypy, pytest
  app/main_api.py | main_worker.py | config.py (pydantic-settings) | logging.py
  app/api/v1/routers/*.py    thin HTTP layer
  app/api/v1/schemas/*.py    request/response DTOs
  app/domain/                models.py, facts.py, enums.py, errors.py   (no I/O)
  app/ingestion/             readers.py, header_detect.py, column_mapper.py, normalize.py, validate.py, consolidate.py
  app/sourcing/              providers/{base,nexar,digikey,mouser,catalog}.py, chain.py, matcher.py, offer_selector.py
  app/pricing/               price_breaks.py, fx.py
  app/risk/                  rules/{data,supply,price}.py, engine.py, narrator.py
  app/impact/                engine.py, scrap_policy.py
  app/alternatives/          finder.py, comparator.py, agent.py
  app/copilot/               graph.py, tools.py, prompts.py, grounding.py
  app/quotation/             builder.py, readiness.py, export_xlsx.py
  app/review/                overrides.py, audit.py
  app/infra/                 firestore/*.py, bigquery_catalog.py, gcs.py, llm.py, jobbus.py, http.py (httpx + retry/breaker)
  tests/{unit,integration,contract}
/data/samples                3 synthetic BOMs + expected results (golden files)
/data/catalog_seed           curated catalog JSONL → BigQuery loader
/infra                       cloudbuild.yaml, deploy.sh, bq schemas, firestore indexes
/docs                        these deliverables
```

### 3.2 Domain models (Pydantic v2, abbreviated)
```python
class Provenance(StrEnum): ACTUAL; CALCULATED; ASSUMED; UNAVAILABLE; RECOMMENDED
class Fact(BaseModel, Generic[T]): value: T | None; provenance: Provenance; evidence_ids: list[str] = []; formula: str | None; note: str | None

class BomLine:          id, line_no, cpn, mpn_raw, mpn: str|None, manufacturer_raw, manufacturer: str|None, description,
                        qty_per: Fact[Decimal], uom, refdes: list[str], dnp: bool,
                        validation: list[Issue], match: MatchResult, selected_offer_id: str|None,
                        substituted_from: str|None, overrides: dict[str, Override], version: int
class MatchResult:      status: MATCHED|AMBIGUOUS|NOT_FOUND|PENDING, component_id, confidence: float, candidates: list[str]
class Offer:            id, line_id, distributor, sku, mpn, manufacturer, authorized: bool, stock: int|None, moq: int|None,
                        order_multiple: int|None, packaging, lead_time_days: int|None, lifecycle: Lifecycle,
                        price_breaks: list[PriceBreak], currency, evidence_id, mode: LIVE|CACHE|DEMO_SNAPSHOT, fetched_at
class Lifecycle(StrEnum): ACTIVE; NRND; LAST_TIME_BUY; EOL; OBSOLETE; UNKNOWN
class Risk:             id, line_id|None, rule_id, category: DATA|SUPPLY|PRICE|LIFECYCLE|QUANTITY, severity: BLOCKER|HIGH|MEDIUM|LOW,
                        title, why: str, evidence_ids, metrics: dict, suggested_actions: list[Action],
                        status: OPEN|ACKNOWLEDGED|RESOLVED|WAIVED, resolution_note, narrative_source: TEMPLATE|LLM
class LineImpact:       volume, required, scrap_pct: Fact, gross, net_need, buy_qty, excess_qty, shortage_qty,
                        unit_price: Fact, extended: Fact, excess_cost: Fact, per_unit_cost: Fact, contribution_pct, trace: list[CalcStep]
class Alternative:      id, line_id, candidate_mpn, manufacturer, source, fit_class: DROP_IN|FUNCTIONAL|NOT_SUITABLE,
                        comparison: list[AttrCompare], offers_summary, delta_cost, delta_lead, explanation, status: PROPOSED|APPROVED|REJECTED, decided_by, note
class QuoteVersion:     version, created_at, status: DRAFT|FINALIZED, volumes: list[VolumeQuote], assumptions, readiness, line_snapshot_ref
```

### 3.3 Firestore layout
```
projects/{pid}                       name, customer, currency, build_quantities[], target_ship_date, status, data_mode,
                                     source_file{gcs_uri, filename, sha256, sheet, header_row}, mapping{}, assumptions{},
                                     stats{lines, matched, risks_by_severity, spend_at_risk_pct, totals_by_volume}, created_at, updated_at
projects/{pid}/lines/{lid}
projects/{pid}/offers/{oid}          indexed by line_id
projects/{pid}/risks/{rid}           indexes: (status, severity), (line_id)
projects/{pid}/alternatives/{aid}    index: (line_id, status)
projects/{pid}/evidence/{eid}
projects/{pid}/quotes/{version}      immutable once FINALIZED
projects/{pid}/chat/{sid}/messages/{mid}
projects/{pid}/audit/{eventId}       actor_role, action, target, before, after, reason, at
jobs/{jid}                           project_id, type, status, stage, progress(0-100), error{code,message}, started_at, finished_at
```

### 3.4 BigQuery
- `catalog.components` (mpn_norm, manufacturer, category, description, params JSON, lifecycle, ltb_date, rohs, datasheet_url, source, snapshot_date)
- `catalog.offers_cache` (mpn_norm, distributor, sku, stock, moq, mult, lead_days, price_breaks ARRAY<STRUCT<qty INT64, price NUMERIC>>, currency, authorized, fetched_at, mode). Partitioned by `DATE(fetched_at)`.
- `catalog.crossrefs` (mpn_norm, alt_mpn, alt_manufacturer, relation: FFF|FUNCTIONAL|UPGRADE, source)
- `analytics.events` (project_id, event, payload JSON, ts). Feeds the stretch "insights" page.

### 3.5 Key algorithms
**Ingestion**
1. Pick the sheet with the most non-empty rows that contain alias hits.
2. Find the header row by scanning the first 25 rows for the row with the most alias matches (handles title blocks).
3. Map columns: exact or fuzzy alias match (rapidfuzz ≥ 90) first. Remaining columns go to Gemini Flash with a JSON schema (`{column → field|null, confidence}`); the prompt says "null if unsure". The user confirms in the mapping UI. Required fields: `mpn` or (`description` + `manufacturer`), plus `qty_per`.
4. Normalize:
   - MPN: trim, uppercase, strip whitespace and invisible characters, keep `-/.#`. Packaging suffixes (`-TR`, `/REEL`) are recorded but kept.
   - Manufacturer: alias table (e.g. "TI" → Texas Instruments).
   - Qty: decimal. Must be > 0; must be an integer for EA.
   - Refdes: expand ranges like `R1-R4`.
5. Validate. Issues: `MISSING_MPN`, `MISSING_MFR`, `QTY_INVALID`, `REFDES_QTY_MISMATCH`, `DUPLICATE_MPN_CONFLICT`, `SUSPECT_MPN_FORMAT` (regex heuristics), `DNP`.
6. Consolidate duplicate MPNs (sum quantities, merge refdes). Mixed UOM is a conflict issue and is never merged silently.

**Sourcing**
- The provider chain runs in parallel per line with `asyncio.gather`, bounded by a semaphore (8).
- Mode order:
  - `live_first`: live calls, then cache on failure.
  - `cache_first`: cache when fresh (< 7 days), then live.
  - `demo_snapshot`: cache only.
- Live results are written through to BigQuery.
- Match: only an exact `mpn_norm` gives MATCHED (confidence < 1 if the manufacturer differs). Fuzzy and prefix near-misses (typos, missing packaging suffixes) are **never auto-matched**: they are returned as `candidates` on a NOT_FOUND result, and the user confirms one via `POST /lines/{lid}/match` (audited). AMBIGUOUS is reserved for live data returning one MPN from several manufacturers.
- **Offer selection** produces a Recommended fact with reasons. Filters: authorized and lifecycle not OBSOLETE. Score:
  `0.45·cost_norm(total buy cost incl. excess) + 0.25·stock_coverage + 0.20·lead_time_norm + 0.10·packaging_fit`
  The top-3 reasons are stored, e.g. "Covers 100% of the 5,000 needed from stock; ₹3.2k cheaper than the next option when MOQ excess is included". The user can override, which writes an audit entry.

**Price break:** the price at the highest break at or below the buy quantity. If the buy quantity is below the first break, that is UNAVAILABLE, unless the first break is at or below MOQ, in which case buy at MOQ. FX is an ASSUMED fact (rate, date, source).

**Impact (per line, per volume V)**
```
required    = qty_per × V                                              [CALCULATED]
scrap_pct   = user override | package-attrition table | price-tier table (≥1.25→1%, ≥0.25→2%, else 5%)   [ASSUMED]
gross       = ceil(required × (1 + scrap_pct))
net_need    = max(0, gross − on_hand)            (on_hand default 0, ASSUMED)
buy_qty     = max(MOQ, ceil(net_need / mult) × mult)
excess_qty  = buy_qty − net_need ; excess_cost = excess_qty × unit_price(buy_qty)
shortage    = max(0, buy_qty − stock_selected_offer)   → feeds lead-time risk
extended    = buy_qty × unit_price(buy_qty) ; per_unit = extended / V ; contribution = extended / Σ extended
break_jump  = cheapest q' ≥ buy_qty over the break points: q'·p(q') < extended → RECOMMENDED "buy q' instead, save X"
```
Each step appends a `CalcStep{label, formula, inputs, output}`, which renders as a calculation trace. Missing inputs make the outputs UNAVAILABLE with a reason; they never become 0.

**Quote:** per volume, material = Σ extended. Optional ASSUMED adders (assembly/unit, NRE, overhead %, margin %) are entered by the user and labelled ASSUMED. The total shows material vs. adders separately.

**Risk rules (initial catalog; each one is a pure function `(line, offers, impact, ctx) → Risk|None`)**
| ID | Rule | Default severity | Evidence |
|---|---|---|---|
| D01 | Missing MPN | BLOCKER | BOM cell |
| D02 | Missing manufacturer | MEDIUM | BOM cell |
| D03 | MPN not found in any source | HIGH | provider responses |
| D04 | Invalid qty / UOM conflict | BLOCKER | BOM cell |
| D05 | Refdes count ≠ qty_per | MEDIUM | BOM cells |
| D06 | Manufacturer mismatch (BOM vs source) | MEDIUM | BOM cell + offer |
| D07 | Ambiguous match | HIGH | candidates |
| L01 | EOL / Obsolete | BLOCKER (no stock) or HIGH | lifecycle from source |
| L02 | NRND / LTB (LTB date < target + 90 days) | HIGH | lifecycle, LTB date |
| S01 | Stock across authorized sources < buy qty | HIGH | offers |
| S02 | Single authorized source | MEDIUM | offers |
| S03 | Lead time > days until target ship date (or an explicit, assumed 84-day horizon when no target is set), when the selected offer's stock can't cover the buy quantity | HIGH | offer lead time, stock |
| S04 | No authorized source (broker only) | HIGH | offers |
| P01 | Price spread > 40% vs cross-source median | MEDIUM | offers |
| P02 | Customer target price > 25% **below** the selected market price (a target above market is not a quoting risk) | MEDIUM | BOM cell + offer |
| P03 | MOQ excess cost > 20% of line cost | MEDIUM | impact trace |
| P04 | Price data stale: LIVE/CACHE offer older than 7 days. DEMO_SNAPSHOT data is disclosed globally (data-mode chip and badges), not flagged per line | LOW | fetched_at |
| P05 | Matched and offered, but no offer can be priced for the order (skipped when the quantity is invalid: D04 explains that) | HIGH | price breaks |
| Q01 | Line > 15% of BOM cost (concentration) | LOW | impact |

- `why` comes from a deterministic template filled with metrics.
- Rules are evaluated at the **primary** (first) build quantity; impact is computed for every volume.
- Risk ids are deterministic (`rsk_<rule>_<line>`), so a user's review (ACKNOWLEDGED, RESOLVED, WAIVED) carries over to re-runs while the risk still applies. Risks whose condition disappears (e.g. a fixed MPN) are removed. Waiving requires a note, and every review is audited.
- The narrator (Gemini Flash, P1, deferred) may rephrase the template but receives only the rule output JSON. A validator rejects any narrative containing numbers absent from the metrics.
- BOM-level output:
  - **ready** = no unresolved (OPEN or ACKNOWLEDGED) BLOCKER. This drives the project status: `QUOTE_READY` or `IN_REVIEW`.
  - **readiness %** = lines without unresolved BLOCKER/HIGH risks ÷ costed lines.
  - **spend at risk** = cost of those lines ÷ material total.
  - Also counts by severity and category, and the top-5 risks by cost exposure.

**Alternatives (LangGraph sub-graph)**
`gather_candidates` (Nexar similarParts, DigiKey substitutions, BQ crossrefs) → `fetch_offers` → `compare` (deterministic param diff by category: package/footprint, value, tolerance, voltage/current rating, temp range, lifecycle, RoHS) → `classify` (DROP_IN if all critical params match; FUNCTIONAL if critical params are within tolerance rules; else NOT_SUITABLE) → `explain` (Gemini Pro sees only the comparison table and offers) → saved as PROPOSED.

Approving an alternate creates a new line version with `substituted_from`, re-runs sourcing, risk and impact for that line, and logs an audit entry. Nothing is ever auto-replaced.

**Copilot (LangGraph ReAct)**
- Tools (read-only, except what-if, which is non-persistent):
  - `get_project_summary`
  - `search_lines(query, filters)`
  - `get_line(line_id)`
  - `get_offers(line_id)`
  - `list_risks(filters)`
  - `get_impact(volume, line_id?)`
  - `list_alternatives(line_id)`
  - `simulate(volume, overrides)` (calls the impact engine)
  - `get_evidence(id)`
- Tool results carry `evidence_ids`.
- System contract:
  - Answer only from tool results.
  - Cite `[E:id]`.
  - Say "Not available in project data" when needed.
  - Never invent prices, stock or lifecycle.
- Grounding post-check: every number in the answer must appear in this turn's tool outputs, or be derived by `simulate`. Otherwise the agent regenerates once, then shows an "unverified" banner.
- Output events over SSE: `token`, `tool_start`, `tool_end`, `citations`, `done`, `error`.
- History is kept in Firestore. The last 10 turns plus a project summary are sent as context.

### 3.6 Frontend
- **Layout:**
  - Top bar with project switcher, role switcher and data-mode chip (LIVE/CACHE/SNAPSHOT)
  - Left stepper (Upload → Map → Analyze → Review → Quote)
  - Main tab area
  - Right copilot drawer, always available
- **Tabs:**
  - **Overview:** readiness gauge, KPIs by volume, risk heatmap, cost Pareto, "next best action" list
  - **BOM:** TanStack Table, quality tiles that filter the table, inline edit with reason (sticky edited highlight)
  - **Sourcing:** per-line offer comparison and recommended badge with reasons
  - **Risks:** grouped list with why, evidence and actions; resolve/waive with a note
  - **Impact:** volume selector, waterfall (material → scrap → MOQ excess → total), per-line calculation trace
  - **Alternatives:** side-by-side parameter diff table; approve/reject
  - **Quote:** versions, readiness checklist, finalize, export XLSX
- `<FactValue>` renders the value, a provenance badge and an evidence popover. This is the one component used everywhere.
- **Guided demo mode** (first-time viewer): one click seeds a sample project. A 7-step coach-mark tour follows the hero flow.

### 3.7 Error handling and resilience
- Error envelope everywhere: typed `DomainError` subclasses map to HTTP codes.
- `httpx` client: retry with exponential backoff (2 tries) on 429/5xx, then a circuit breaker per provider (opens after 5 failures, for 60s).
- Jobs are idempotent (keyed by `job_id`); stage checkpoints live in the Firestore job doc.
- Partial failure is shown as data, not hidden. Example: "DigiKey unavailable; using cache from 2026-10-14", recorded as evidence.

### 3.8 Testing strategy
- **Unit:** parsers, normalizers, every risk rule, the impact engine (property-based with Hypothesis: buy_qty ≥ net_need, excess ≥ 0) and offer scoring.
- **Golden tests:** each sample BOM produces the expected risks, totals and impact (JSON snapshots).
- **Contract:** schemathesis against `openapi.yaml`. Provider adapters are tested with recorded fixtures (respx).
- **Integration:** Firestore and Pub/Sub emulators plus a BigQuery fake layer, running the pipeline end to end.
- **LLM:** a fake chat model in CI. A small eval set (10 copilot questions with expected citations) runs manually against Gemini.
- **E2E:** Playwright smoke run of the hero flow against the deployed URL (pre-demo checklist).

---

## 7. Sample data plan (for demo and tests)

1. **`motor_controller.xlsx`** (~60 lines, hero BOM), seeded with:
   - 1 EOL part with low stock, which has a drop-in alternate
   - 1 NRND part
   - 1 single-source part
   - 1 part with a 16-week lead time
   - 1 price outlier
   - 1 reel-only MOQ excess part, with a price-break jump opportunity
   - 1 MPN typo (not found)
   - 1 missing manufacturer
   - 1 refdes/qty mismatch
   - 1 duplicate MPN
2. **`iot_sensor.csv`** (~35 lines, mostly clean) to show the happy path.
3. **`messy_format.xlsx`**: title block, merged headers and odd column names, to show AI mapping.

Each BOM uses real, common MPNs. The curated catalog snapshot has dated `fetched_at` values and is labelled **DEMO_SNAPSHOT** in the UI, so nothing is passed off as live data. Golden expected outputs are stored next to each file.
