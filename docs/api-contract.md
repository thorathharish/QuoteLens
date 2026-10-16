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
| 3 | `GET /projects/{pid}/overview` | Readiness and KPIs | → `{status, data_mode, currency, lines, matched, unpriced_lines, totals_by_volume[{volume, material, total, per_unit}: Fact], risks: RiskSummary{by_severity, unresolved_by_severity, open_blockers, ready, readiness_pct, spend_at_risk_pct, top_exposure}, next_actions[{label, risk_id, line_id}]}` |
| 4 | `GET`/`PUT /projects/{pid}/assumptions` | Scrap policy, FX, adders (audited; re-computes impact and risks) | `{scrap_policy{mode: price_tier\|package\|fixed, fixed_pct, tiers[]}, fx_overrides{"USD->INR": rate}, adders{assembly_per_unit, nre, overhead_pct, margin_pct}}` → `Assumptions` |
| **BOM ingestion** |||
| 5 | `POST /projects/{pid}/bom` | Upload (multipart `file`) | → `200 {upload_id, filename, sheets[], selected_sheet, header_row (1-based), data_rows, proposed_mapping[{column_index, header, field, confidence, method: ALIAS\|LLM\|USER\|NONE, reason}], preview_rows[][], unmapped[], warnings[]}` |
| 6 | `PUT /projects/{pid}/bom/mapping` | Confirm mapping (gate 1) | `{upload_id, mapping[{column_index, field\|null}] (overrides only), sheet?, header_row?}` → `202 {job_id}` (parse, validate, then analysis). `422` lists missing required columns. |
| 7 | `GET /jobs/{job_id}` | Progress | → `{status: QUEUED\|RUNNING\|SUCCEEDED\|FAILED, stage, progress, warnings[], error?}` |
| 8 | `POST /projects/{pid}/analysis` | Re-run (all or `line_ids`) | `{line_ids?, refresh_live?: bool}` → `202 {job_id}` |
| **Lines and sourcing** |||
| 9 | `GET /projects/{pid}/lines` | Table | `?issue=&risk_severity=&match_status=&q=&sort=` → `Page<LineRow>` |
| 10 | `GET /projects/{pid}/lines/{lid}` | Line detail | → `{line, component, offers[], selected_offer, recommendation{offer_id, score, volume, reasons[]}, evidence{id→Evidence}, risks[], impact_by_volume[], alternatives[]}` (the last three are filled in Phases 4–5) |
| 11 | `PATCH /projects/{pid}/lines/{lid}` | Correct data (audited) | `{changes{mpn?, manufacturer?, qty_per?, uom?, dnp?}, reason}` → `{line, triggered_job_id}` |
| 12 | `POST /projects/{pid}/lines/{lid}/match` | Correct the MPN or accept a suggested candidate (audited; the line is re-sourced at once) | `{mpn, manufacturer?, reason}` → `LineDetail` |
| 13 | `GET /projects/{pid}/lines/{lid}/offers` | Compare offers | → `{offers[Offer], recommendation{offer_id, score, volume, reasons[]}}` |
| 14 | `PUT /projects/{pid}/lines/{lid}/selected-offer` | Override selection | `{offer_id, reason}` → `LineDetail` |
| 15 | `GET /components/lookup` | Ad-hoc part lookup | `?mpn=&mode=` → `{mpn, component, offers[], suggestions[], warnings[]}` |
| **Risks** |||
| 16 | `GET /projects/{pid}/risks` | List | `?status=&severity=&category=&line_id=` → `{summary: RiskSummary, items: Risk[]}` (sorted by severity, then cost exposure) |
| 17 | `GET /projects/{pid}/risks/{rid}` | Detail plus evidence | → `{risk, evidence{id→Evidence}}` |
| 18 | `PATCH /projects/{pid}/risks/{rid}` | Review (gate 2) | `{status: ACKNOWLEDGED\|RESOLVED\|WAIVED, note}` (note required for WAIVED) → `Risk` |
| **Impact** |||
| 19 | `GET /projects/{pid}/impact` | Per volume (default: primary) | `?volume=` → `{volume, currency, totals{required_material, scrap_cost, excess_cost, material, adders, grand_total, per_unit}: Fact, waterfall[], lines[LineImpact with trace], recommendations[PRICE_BREAK_JUMP], unpriced_line_ids[]}` |
| 20 | `POST /projects/{pid}/impact/simulate` | What-if (never saved) | `{volume, overrides[{line_id, scrap_pct?, offer_id?, qty_per?, on_hand?}]}` → `{baseline, simulated, delta: Fact}` |
| **Alternatives** |||
| 21 | `POST /projects/{pid}/lines/{lid}/alternatives/search` | Investigate (LangGraph: cross-refs → offers → parameter comparison → fit class → explanation) | `{reason?}` → `202 {job_id}`; the job warns when no alternates are known |
| 22 | `GET /projects/{pid}/alternatives` | Queue | `?line_id=&status=` → `{items: Alternative[{candidate_mpn, manufacturer, fit_class, comparison[{attribute, original, candidate, critical, result}], offers_summary, delta_cost, delta_lead_days, explanation, evidence_ids, status}]}` |
| 23 | `POST /projects/{pid}/alternatives/{aid}/decision` | Approve/reject (gate 3; audited) | `{decision: APPROVE\|REJECT, note (required)}` → `{alternative, line}`. APPROVE creates a line version with `substituted_from` and re-sources it. `409` for a NOT_SUITABLE candidate. |
| **Copilot** |||
| 24 | `POST /projects/{pid}/chat/sessions` | New session | `{line_id?, risk_id?}` (focus) → `201 ChatSession` |
| 25 | `POST /projects/{pid}/chat/sessions/{sid}/messages` | Ask (SSE; rate-limited to 10/min per client) | `{content}` → `text/event-stream`: `tool_start{name,args}` · `tool_end{name}` · `token{text}` (streamed only **after** the grounding check) · `citations{items[{evidence_id,label}]}` · `done{message_id, grounded, unverified_numbers[]}` · `error{code,message}`. `503 LLM_UNAVAILABLE` without Gemini. |
| 26 | `GET /projects/{pid}/chat/sessions/{sid}/messages` | History | → `{items: ChatMessage[{role, content, citations, tool_calls, grounded}]}` |
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
