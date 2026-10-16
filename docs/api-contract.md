# API Contract

> QuoteLens · AI Builder Cup 2026 · Manufacturing track. Part of the design package; see [README](README.md).

## 6. API contract (summary; full `openapi.yaml` is generated from FastAPI)

**Conventions**
- Base path: `/api/v1`, JSON, `snake_case`.
- Header `X-Demo-Role` (audit only). `X-Request-Id` is echoed back.
- `Idempotency-Key` on job-creating POSTs.
- Cursor pagination: `?limit=50&cursor=`.
- Money is a decimal string plus a `currency` field.
- Any value can be a `Fact`.
- Error envelope:
  `{"error": {"code": "QUOTE_HAS_OPEN_BLOCKERS", "message": "...", "details": {...}, "request_id": "..."}}`
- Error codes: `VALIDATION_ERROR` 422, `NOT_FOUND` 404, `CONFLICT` / `INVALID_STATE` 409, `UNSUPPORTED_FILE` 415, `FILE_TOO_LARGE` 413, `UPSTREAM_UNAVAILABLE` 503 (with degraded-data note), `LLM_UNAVAILABLE` 503, `RATE_LIMITED` 429.

| # | Method & path | Purpose | Request → Response |
|---|---|---|---|
| **Projects** |||
| 1 | `POST /projects` | Create | `{name, customer?, currency, build_quantities:[int], target_ship_date?, data_mode?}` → `201 Project` |
| 2 | `GET /projects` · `GET /projects/{pid}` · `DELETE /projects/{pid}` | List / get / delete | → `Page<ProjectSummary>` / `Project` / `204` |
| 3 | `GET /projects/{pid}/overview` | Readiness and KPIs | → `{status, readiness{pct, open_blockers}, totals_by_volume[Fact], risks_by_severity, spend_at_risk_pct, next_actions[]}` |
| 4 | `PUT /projects/{pid}/assumptions` | Scrap, FX, adders | `{scrap_policy, fx_overrides, adders{assembly_per_unit?, nre?, overhead_pct?, margin_pct?}}` → `Assumptions` |
| **BOM ingestion** |||
| 5 | `POST /projects/{pid}/bom` | Upload (multipart `file`) | → `200 {upload_id, sheets[], selected_sheet, header_row, proposed_mapping[{column, field, confidence, method: ALIAS\|LLM\|NONE}], preview_rows[], unmapped[]}` |
| 6 | `PUT /projects/{pid}/bom/mapping` | Confirm mapping (gate 1) | `{upload_id, sheet, header_row, mapping{column→field}}` → `202 {job_id}` (parse, validate, then analysis) |
| 7 | `GET /jobs/{job_id}` | Progress | → `{status: QUEUED\|RUNNING\|SUCCEEDED\|FAILED, stage, progress, warnings[], error?}` |
| 8 | `POST /projects/{pid}/analysis` | Re-run (all or `line_ids`) | `{line_ids?, refresh_live?: bool}` → `202 {job_id}` |
| **Lines and sourcing** |||
| 9 | `GET /projects/{pid}/lines` | Table | `?issue=&risk_severity=&match_status=&q=&sort=` → `Page<LineRow>` |
| 10 | `GET /projects/{pid}/lines/{lid}` | Line detail | → `{line, offers[], selected_offer, risks[], impact_by_volume[], alternatives[], evidence_index}` |
| 11 | `PATCH /projects/{pid}/lines/{lid}` | Correct data (audited) | `{changes{mpn?, manufacturer?, qty_per?, uom?, dnp?}, reason}` → `{line, triggered_job_id}` |
| 12 | `POST /projects/{pid}/lines/{lid}/match` | Resolve ambiguous match | `{component_id \| mpn}` → `LineDetail` |
| 13 | `GET /projects/{pid}/lines/{lid}/offers` | Compare offers | → `{offers[Offer], recommended{offer_id, score, reasons[]}}` |
| 14 | `PUT /projects/{pid}/lines/{lid}/selected-offer` | Override selection | `{offer_id, reason}` → `LineDetail` |
| 15 | `GET /components/lookup` | Ad-hoc part lookup | `?mpn=&manufacturer=&mode=` → `{component, offers[], evidence[]}` |
| **Risks** |||
| 16 | `GET /projects/{pid}/risks` | List | `?status=&severity=&category=&line_id=` → `{summary, items: Page<Risk>}` |
| 17 | `GET /projects/{pid}/risks/{rid}` | Detail plus evidence | → `Risk & {evidence[]}` |
| 18 | `PATCH /projects/{pid}/risks/{rid}` | Review (gate 2) | `{status: ACKNOWLEDGED\|RESOLVED\|WAIVED, note}` (note required for WAIVED) → `Risk` |
| **Impact** |||
| 19 | `GET /projects/{pid}/impact` | Per volume | `?volume=1000` → `{volume, totals{material, scrap_cost, excess_cost, adders, grand_total}[Fact], waterfall[], lines[LineImpact], recommendations[]}` |
| 20 | `POST /projects/{pid}/impact/simulate` | What-if (not saved) | `{volume, overrides[{line_id, scrap_pct?, offer_id?, qty_per?, on_hand?}]}` → `ImpactResult & {delta_vs_baseline}` |
| **Alternatives** |||
| 21 | `POST /projects/{pid}/lines/{lid}/alternatives/search` | Investigate | `{reason?, constraints?{same_package?:bool, max_lead_days?}}` → `202 {job_id}` |
| 22 | `GET /projects/{pid}/alternatives` | Queue | `?line_id=&status=` → `Page<Alternative>` |
| 23 | `POST /projects/{pid}/alternatives/{aid}/decision` | Approve/reject (gate 3) | `{decision: APPROVE\|REJECT, note}` → `{alternative, line?, triggered_job_id?}` |
| **Copilot** |||
| 24 | `POST /projects/{pid}/chat/sessions` | New session | `{focus?{line_id?, risk_id?}}` → `{session_id}` |
| 25 | `POST /projects/{pid}/chat/sessions/{sid}/messages` | Ask (SSE) | `{content}` → `text/event-stream`: `tool_start{name,args}` · `tool_end{name,evidence_ids}` · `token{text}` · `citations[{evidence_id,label}]` · `done{message_id, grounded: bool}` · `error{code}` |
| 26 | `GET /projects/{pid}/chat/sessions/{sid}/messages` | History | → `Page<Message>` |
| **Quotes** |||
| 27 | `POST /projects/{pid}/quotes` | Snapshot version | `{note?}` → `201 QuoteVersion` (includes readiness) |
| 28 | `GET /projects/{pid}/quotes` · `/{version}` | List / get | → `Page<QuoteSummary>` / `QuoteVersion` |
| 29 | `POST /projects/{pid}/quotes/{version}/finalize` | Gate 4 | `{note}` → `QuoteVersion`. `409 QUOTE_HAS_OPEN_BLOCKERS` with the list. |
| 30 | `GET /projects/{pid}/quotes/{version}/export` | Download | `?format=xlsx` → `{download_url (signed, 15 min)}` |
| **Evidence, audit, demo, health** |||
| 31 | `GET /projects/{pid}/evidence/{eid}` | Source detail | → `Evidence` |
| 32 | `GET /projects/{pid}/audit` | Decision trail | → `Page<AuditEvent>` |
| 33 | `POST /demo/projects` | Seed scenario | `{scenario: motor_controller\|iot_sensor\|messy_format}` → `201 {project_id, job_id}` |
| 34 | `GET /healthz` · `GET /readyz` | Probes | → `{status, deps{firestore, bigquery, vertex, providers{...}}}` |
| **Worker (internal)** |||
| 35 | `POST /internal/jobs/pubsub` | Pub/Sub push (OIDC verified) | Pub/Sub envelope → `204` |
