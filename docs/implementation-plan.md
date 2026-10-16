# Implementation Plan

> QuoteLens · AI Builder Cup 2026. Part of the design package; see [README](README.md). Approved 2026-10-16.


## Context
The design package (architecture, HLD, LLD, user flows, competitors, API contract, ADRs) is approved and on GitHub (`thorathharish/QuoteLens`, `docs/`). This plan turns it into a working, deployed demo of the 7 capabilities, ready for the AI Builder Cup 2026 submission. About **48 hours** remain (closes around 2026-10-18 late evening IST).

**Scope rules**
- **No Gerber/PCB work of any kind.** We will not parse Gerber or PCB files, and we will not reuse anything from the reference repo's `gerber-integration/` folder (its BOM parser, `package_map.yaml`, `component_intel`). The column aliases, header detection, refdes expansion and package-attrition table are written fresh.
- The source of truth is `docs/` (LLD §3, API contract, `openapi.yaml`).
- Priority tiers: **P0** must work in the demo · **P1** should have · **P2** stretch, cut first if time runs out.
- **Budget: GCP free credits only.** Every design and deploy choice must fit the free credits and the Always Free tier. See the [free-credit cost plan](#free-credit-cost-plan) below.

---

## Free-credit cost plan
The free trial gives **$300 of credit for 90 days**. Paid services draw it down after any Always Free allowance is used. Two consequences:
- **Gemini on Vertex AI is covered.** The credit can't pay for the Gemini API in AI Studio or for partner models offered as a managed API (e.g. third-party LLMs on Vertex). We therefore use **Gemini through Vertex AI only**.
- **Check the dates.** If the account is not upgraded when the trial ends, billing closes and resources stop. Confirm the trial end date is after judging.

Limits from [Google Cloud's Free Tier page](https://docs.cloud.google.com/free/docs/free-cloud-features), checked 2026-10-16:

| Service | Always Free (per month unless noted) | How we stay inside it |
|---|---|---|
| **Cloud Run** | 2M requests; 180,000 vCPU-seconds; 360,000 GB-seconds; 1 GB egress (North America) | `min-instances=0` everywhere during development. 1 vCPU; 512 MiB for web, 1 GiB for api and worker. `max-instances` 3 for api and web, 2 for the worker. CPU is allocated only during requests. `min-instances=1` for web and api **only during the demo window**, switched off afterwards. |
| **Firestore** | 1 GiB storage; **50,000 reads, 20,000 writes, 20,000 deletes per day** | One BOM line per doc, never one per cell. Batched writes of up to 500. The UI polls job status every 2–3s, only while a job runs. Overviews read precomputed `stats` on the project doc. The api caches line lists for the duration of a request. |
| **BigQuery** | 1 TiB queries; 10 GiB storage | The catalog is at most about 10 MB. One batched `IN UNNEST(@mpns)` query per analysis. Select explicit columns, never `SELECT *`. `offers_cache` is partitioned and queried with a date filter. Data goes in through **load jobs** (free), not streaming inserts. |
| **Cloud Storage** | 5 GB-months regional storage (**us-central1, us-east1 or us-west1 only**); 5k Class A / 50k Class B ops | One bucket in `us-central1`. A lifecycle rule deletes `exports/` after 7 days. Uploads are capped at 5 MB. |
| **Pub/Sub** | 10 GiB of messages | Messages carry IDs only (a few hundred bytes); no payloads. |
| **Cloud Build** | 2,500 build-minutes (e2-standard-2) | Build only on a deploy (manual trigger or tag), not on every push. Docker layer caching via `--cache-from`. |
| **Artifact Registry** | 0.5 GB storage | Slim images (python-slim, Next.js standalone). A cleanup policy keeps the last 3 images per service. |
| **Secret Manager** | 6 active secret versions; 10,000 access ops | At most 6 secrets (DigiKey id and secret, Mouser key, Nexar id and secret, one spare). Read once at startup and kept in memory. Old versions are disabled. |
| **Cloud Logging** | First 50 GiB per project | INFO level in production. No request or response bodies are logged. |
| **Vertex AI (Gemini)** | **Not free.** Paid from the credit. | The main cost. See the Gemini controls below. |

**Gemini controls (the main spend)**
- **Flash by default** for header mapping, risk narration and the copilot. **Pro only** for alternate-part explanations, and it can be set to Flash in config (`GEMINI_PRO_MODEL`).
- **Token caps:** `max_output_tokens` is 1024 for the copilot and 512 for narration and mapping. Copilot history is limited to the last 6 turns plus a compact project summary. Tool outputs are trimmed to the fields that matter.
- **Call less often:**
  - Header mapping is cached per file sha256, and the LLM is called only for columns the aliases didn't match.
  - Risk narratives are generated once per risk and stored.
  - Alternate explanations are generated only when someone asks.
  - The copilot agent stops after 6 tool calls.
- **No LLM calls in tests or CI.** A fake chat model is used. The 10-question eval set is run by hand only a few times.
- **Kill switch:** `LLM_ENABLED=false` keeps everything working on templates.

**Not used, because they are expensive or bill while idle:** Dataflow, Cloud SQL, GKE, Memorystore, custom Vertex AI model endpoints, Vertex AI Search, Cloud Load Balancing and Cloud NAT. Cloud Run's default `*.run.app` URLs are enough. Dataflow is replaced by the Pub/Sub plus Cloud Run worker pipeline (ADR-0006).

**Guardrails (Phase 0)**
- A dedicated GCP project for the hackathon.
- A Billing budget with alerts at 25, 50, 75 and 90% of the credit.
- A `infra/cost-check.md` checklist to review daily: Billing reports filtered by SKU, watching Vertex AI and Cloud Run.
- Cloud Run `max-instances` caps and a per-IP rate limit on the copilot endpoint (10 requests/min in middleware).
- After judging, `infra/teardown.sh` deletes the services, bucket, BigQuery datasets and Artifact Registry images, or the whole project.

**Reference repo** (`C:\Users\Asus\Downloads\BuLLMQuote_SRIM-main\BuLLMQuote_SRIM-main\`). Ideas only, rewritten with tests:
- `mcp-tools/intake/bom_processing.py`
  - LLM header-mapping prompt pattern (:111): fixed fields, null if unsure
  - Unit-normalisation maps (:59-104)
  - Consolidate-by-MPN that refuses mixed units (:614)
- `mcp-tools/distributor-pricing/`
  - `models.py:12` `select_price_for_qty`
  - `enrichment.py:36` `effective_moq`
  - `digikey_client.py`: OAuth2 token handling and Cut-Tape preference
  - `element14.py:22-47`: status-code maps
- `mcp-tools/reporting/superset/`
  - `scrap_factor.py`: price-tier scrap %
  - `queries.py:755-823`: excess-inventory chain
  - `reports/missing_notes.py`: risk checklist ideas
- `accomplish-ui/apps/daemon/src/rfq-chat/rfq-chat-prompt.ts:26`: "no answer" sentinel and citations taken from retrieval

---

## Team tracks (4 members, run in parallel)
| Track | Owner focus | Phases |
|---|---|---|
| **A: Backend core** | Domain, ingestion, sourcing, impact, risk, quote | 0, 2, 3, 4, 7 |
| **B: Frontend** | Next.js app, all screens, guided demo | 8 (starts at hour 2 against mocks) |
| **C: Data + infra** | Sample BOMs, catalog, BigQuery, GCP, CI/CD, deploy | 0 (GCP), 1, 9 |
| **D: AI** | Gemini mapping, alternatives agent, copilot, evals, pitch | 2 (LLM mapper), 5, 6, pitch deck |

## Milestones
| Milestone | When (from start) | Exit criteria |
|---|---|---|
| **M1: Walking skeleton** | +8h | web, api and worker deployed on Cloud Run (health OK); sample data in BigQuery; CI green |
| **M2: Backend journey** | +22h | Via API alone: upload motor_controller → mapping → analysis → risks → impact → quote finalize. Golden tests pass. |
| **M3: Full product** | +34h | UI hero flow on the deployed URL; copilot and alternatives work |
| **M4: Code freeze** | +42h | Only bug fixes after this. Smoke tests green. Demo rehearsed twice. |
| **Submit** | +46h | Video, deck, repo README, live URL |

---

## Phase 0: Foundations (P0, about 3h, tracks A and C)
**Repo and tooling**
- Monorepo layout per LLD §3.1:
  - `apps/web` (pnpm, Next.js 15, TS strict, ESLint, Tailwind, shadcn/ui)
  - `services/api` (uv, Python 3.12, ruff, mypy, pytest)
  - `data/`, `infra/`
- `.env.example`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml` (lint, typecheck, test for both apps).
- Docs cleanup: remove the `gerber-integration` references from `docs/architecture.md` (the reference-code section) and `docs/lld.md` (any package-attrition mention that came from it).

**Backend skeleton** (`services/api/app/`)
- `config.py`: pydantic-settings with `DATA_MODE`, `JOB_BACKEND`, `GCP_PROJECT`, `GCP_REGION`, `GEMINI_FLASH_MODEL`, `GEMINI_PRO_MODEL`, `USE_EMULATORS`.
- `logging.py`: structured JSON logs with `request_id`, `project_id` and `job_id` context.
- `domain/`
  - `enums.py`: Provenance, Severity, Lifecycle, …
  - `facts.py`: `Fact[T]`, `Evidence`, plus helpers `actual()`, `calculated()`, `assumed()`, `unavailable()`, `recommended()`
  - `models.py`: all LLD §3.2 models
  - `errors.py`: `DomainError` hierarchy mapped to the error envelope
- `infra/repositories/`
  - `base.py`: Protocols such as `ProjectRepo`, `LineRepo`, `OfferRepo`, …
  - `memory.py`: in-memory implementations for tests and offline dev
  - `firestore.py`: real implementations
  - Choice comes from config via `deps.py`.
- `infra/jobbus.py`: the `JobBus` Protocol with `InlineJobBus` and `PubSubJobBus`.
- `main_api.py` and `main_worker.py`:
  - App factories, error handlers, request-id middleware and CORS.
  - `/healthz` and `/readyz` on the api; `/internal/jobs/pubsub` on the worker (OIDC check).

**GCP bootstrap** (track C, `infra/bootstrap.sh`, idempotent gcloud)
- Enable APIs: run, firestore, bigquery, pubsub, storage, aiplatform, secretmanager, cloudbuild, artifactregistry.
- Create:
  - Service accounts `quotelens-api`, `quotelens-worker`, `quotelens-web` with least-privilege roles
  - GCS bucket `uploads/`, `exports/`
  - Firestore (native mode)
  - BigQuery datasets `catalog`, `analytics`
  - Pub/Sub topic `analysis-jobs` with a push subscription to the worker (OIDC, dead-letter topic)
  - Artifact Registry repo
- Region: `us-central1` for every service. It has the widest Gemini availability, and it is one of the regions that qualify for free Cloud Storage.
- Cost guardrails: a Billing budget with 25, 50, 75 and 90% alerts; a GCS lifecycle rule on `exports/`; an Artifact Registry cleanup policy (keep 3); and `infra/teardown.sh`.
- Config adds `LLM_ENABLED`, `LLM_MAX_OUTPUT_TOKENS` and `COPILOT_MAX_TOOL_CALLS`.

**Done when** CI is green, `pytest` runs, and the api answers `/healthz` locally and on Cloud Run (M1, together with Phase 9a).

---

## Phase 1: Sample data and catalog (P0, about 4h, track C)
- `data/samples/`:
  - `motor_controller.xlsx`, about 60 lines, with every issue seeded per LLD §7
  - `iot_sensor.csv`, about 35 clean lines
  - `messy_format.xlsx`: title block and odd headers
  - Each has `*.expected.json` golden outputs (risks by rule_id, matched counts, per-volume material totals).
- `data/catalog_seed/`:
  - `components.jsonl` (about 150 real MPNs: the BOM parts plus their alternates; category, params, lifecycle, ltb_date)
  - `offers.jsonl` (2–3 distributors per part with price breaks, stock, MOQ, multiple, lead time; `mode=DEMO_SNAPSHOT`, dated `fetched_at`)
  - `crossrefs.jsonl`
- `infra/bq/schemas/*.json` and `services/api/scripts/load_catalog.py`, which loads idempotently with `WRITE_TRUNCATE` and validates every row with Pydantic before load.
- `scripts/warm_cache.py` (P1): if distributor keys exist, fetches live offers for every sample MPN into `offers_cache` (`mode=LIVE`), so the demo can show real data.
- **Done when** the BigQuery tables are loaded and the row counts and Pydantic validation pass.

## Phase 2: Ingestion (Capability 1) (P0, about 5h, track A plus D for the LLM mapper)
In `app/ingestion/`:
- `readers.py`
  - XLSX (openpyxl, `read_only`, `data_only`) plus CSV/TSV with delimiter sniffing.
  - Rejects files over 5MB, wrong extension or MIME type.
- `aliases.py`: our own field → alias dictionary for cpn, mpn, manufacturer, description, qty_per, uom, refdes, dnp, unit_price, package, value, notes.
- `header_detect.py`: picks the sheet and header row by best alias score over the first 25 rows.
- `column_mapper.py`
  - Exact or fuzzy alias match first (rapidfuzz ≥ 90).
  - Otherwise a `GeminiHeaderMapper` (LangChain `ChatGoogleGenerativeAI(vertexai=True).with_structured_output`; `ChatVertexAI` is deprecated; prompt says "null if unsure"; header names and sample values passed as JSON data).
  - Falls back to `NONE` if the LLM is unavailable.
- `normalize.py`: MPN, manufacturer alias table, qty (Decimal), UOM map, refdes range expansion.
- `validate.py`: issue codes per LLD.
- `consolidate.py`: duplicate MPNs are merged; mixed UOM produces a `UOM_CONFLICT` issue instead.
- Every parsed value is an `actual()` Fact with a `BOM_CELL` evidence (`sheet!A12`).

API (`api/v1/routers/projects.py`, `bom.py`, `jobs.py`, `lines.py`): endpoints #1–2, #5–7 and a basic #9 (lines list). The upload is stored in GCS with its sha256. #3 (overview) moves to Phase 4, where readiness exists.

**Tests:** unit tests per module; header detection on `messy_format`; a fake LLM mapper; golden check that the parsed line count matches the expected value.

## Phase 3: Sourcing and pricing (Capability 2) (P0 core / P1 live adapters, about 5h, track A)
In `app/sourcing/`:
- `providers/base.py`: `OfferProvider` Protocol, `ProviderResult` (offers, evidence, errors).
- `providers/catalog.py` (P0): one batched BigQuery query using `IN UNNEST(@mpns)`; an in-memory variant for tests.
- `providers/digikey.py`, `mouser.py`, `nexar.py` (P1, only when keys are in Secret Manager): httpx async; DigiKey OAuth2 token cache; Mouser exact-MPN check; responses mapped to `Offer`. Tests use recorded fixtures (respx).
- `infra/http.py`: retry (2 attempts on 429/5xx), a 4s timeout and a per-provider circuit breaker.
- `chain.py`: the three `DATA_MODE` orders; write-through to `offers_cache`; a semaphore of 8.
- `matcher.py`: MATCHED, AMBIGUOUS or NOT_FOUND, with a confidence score.
- `offer_selector.py`: filters plus weighted score; returns a `recommended()` Fact with its top 3 reasons.

In `app/pricing/`:
- `price_breaks.py` (`unit_price_at(qty)`; below the first break gives UNAVAILABLE)
- `fx.py` (assumed rate, with date)

`app/jobs/analysis.py` is the staged pipeline: parse → source → select → impact → risk → stats. Progress and checkpoints go to `jobs/{id}`, and it is idempotent. Endpoints #8, #9–10, #12–15.

**Tests:** selector scoring, the price-break edge cases, chain fallback when a provider raises, and that the pipeline finishes on all 3 samples with the in-memory repos.

## Phase 4: Manufacturing impact and risk (Capabilities 4 and 3) (P0, about 6h, track A)
**`app/impact/`**
- `scrap_policy.py`: price-tier default (≥1.25 → 1%, ≥0.25 → 2%, else 5%), a fixed override, and our own small package-attrition table (0402/0603/QFN/BGA …).
- `engine.py`: the LLD §3.5 formulas. Every step appends a `CalcStep`; any missing input becomes UNAVAILABLE with a reason. Also covers break-jump recommendations, roll-up, contribution % and adders (ASSUMED).
- Endpoints #4, #19, #20.

**`app/risk/`**
- `rules/{data,lifecycle,supply,price,quantity}.py`: all 19 rules as pure functions returning a `Risk` with metrics, evidence and actions.
- `engine.py`: runs the rules and computes the summary, readiness, spend-at-risk and top-5 exposure.
- `narrator.py`:
  - P0: deterministic templates.
  - P1: Gemini Flash rephrasing, guarded by a number-whitelist validator that falls back to the template.
- Endpoints #16–18. A waive without a note returns 422. Risk status changes are written to the audit log.

**Tests**
- Each rule has positive and negative cases.
- Impact engine invariants: buy ≥ net_need, excess ≥ 0, and MOQ and multiple are respected.
- P1: Hypothesis property tests.
- Golden risk and total checks on `motor_controller`.

## Phase 5: Alternative parts (Capability 6) (P0 using catalog crossrefs; P1 live substitutes; about 4h, track D)
In `app/alternatives/`:
- `finder.py`: BigQuery `crossrefs` (P0), plus DigiKey substitutions and Nexar similar parts (P1).
- `comparator.py`: per-category critical-parameter rules giving MATCH, WITHIN_TOLERANCE, MISMATCH or UNKNOWN.
- `classify()`: DROP_IN, FUNCTIONAL or NOT_SUITABLE.
- `agent.py`: a LangGraph `StateGraph`:
  - Nodes: gather → fetch_offers → compare → classify → explain.
  - `explain` uses Gemini Pro and sees only the comparison table and offers; template fallback.
- Decision service (endpoint #23):
  - APPROVE creates a new line version with `substituted_from` and re-runs that line's analysis.
  - REJECT stores the reason.
  - Both are audited. Nothing is ever auto-replaced.
- Endpoints #21–23.

**Tests:** comparator rules; graph run with a fake LLM; approval re-prices the line, and the EOL risk is gone afterwards.

## Phase 6: Evidence-backed copilot (Capability 5) (P0, about 5h, track D)
In `app/copilot/`:
- `tools.py`: the 9 tools from the LLD. They are thin wrappers over the existing services, return JSON with `evidence_ids`, and are read-only except `simulate`.
- `prompts.py`: the system contract (answer only from tools, cite `[E:id]`, say "Not available in project data" when needed). BOM text is treated as data.
- `graph.py`: LangGraph ReAct (`create_react_agent`) with `ChatGoogleGenerativeAI(vertexai=True)` on Gemini Pro (Flash fallback); history from Firestore with the last 10 turns.
- `grounding.py`:
  - Extracts the numbers in the answer and checks they appear in the turn's tool outputs.
  - On failure it regenerates once, then sets `grounded=false`.
  - Citations are kept only if the id was actually returned by a tool.
- SSE endpoint #25 (`sse-starlette`) emits `tool_start`, `tool_end`, `token`, `citations`, `done` and `error`. Endpoints #24 and #26.
- `tests/evals/copilot_questions.yaml`: 10 demo questions with expected tools and citations. Run manually against Gemini; CI uses a fake model.

## Phase 7: Quotation, review and audit (Capability 1 finalization) (P0, about 3h, track A)
- `app/quotation/builder.py`: an immutable version snapshot (volumes, assumptions, readiness, lines reference).
- `readiness.py`: open blockers prevent finalizing; waived risks are listed.
- `export_xlsx.py`: openpyxl workbook with Summary, Lines (provenance column), Risks and Assumptions sheets; saved to GCS; returned as a 15-minute signed URL.
- `app/review/`:
  - Line PATCH (#11) with reason, transaction and audit entry, and a partial re-run.
  - Offer override (#14).
  - Audit list (#32) and evidence (#31).
- Demo seeding (#33): creates a project from a sample file and auto-confirms the alias mapping. P1: a `reset` option.
- Endpoints #27–30.

## Phase 8: Frontend (all capabilities) (P0, about 14h spread over the build, track B)
- **Setup** (hour 2): `openapi-typescript` generates `lib/api/types.ts` from `docs/openapi.yaml` (later from the live `/openapi.json`); typed fetch client; TanStack Query; MSW mocks so screens can be built before the api is ready.
  - BFF route `app/api/[...path]/route.ts` proxies to the api, adds `X-Demo-Role`, and streams SSE through.
- **Core components:**
  - `components/fact/`: `FactValue`, `ProvenanceBadge`, `EvidenceDrawer`
  - `components/layout/`: TopBar (project switcher, role switcher, data-mode chip), Stepper, `CopilotDrawer`
- **Screens, in priority order:**
  1. Landing with "Run guided demo" and a new-project form
  2. Upload and mapping wizard (confidence chips, editable mapping, preview)
  3. Analysis progress (job polling)
  4. Overview (readiness gauge, totals by volume, risk counts, next actions)
  5. Risks (grouped list, why/evidence/actions, resolve/waive dialog)
  6. BOM table (quality tiles, inline edit with reason, edited-cell highlight)
  7. Line detail and sourcing (offer comparison, recommended reasons, override)
  8. Impact (volume selector, waterfall chart, per-line calculation trace)
  9. Alternatives (parameter diff table, approve/reject)
  10. Quote (versions, readiness checklist, finalize, export)
  11. Copilot drawer (streaming, tool chips, citation chips open the evidence)
  12. P1: guided tour (7 coach marks along the hero flow)
- **Tests:** Vitest for `FactValue` and the formatters. A Playwright `hero-flow.spec.ts` runs against local and deployed URLs.

## Phase 9: Deploy, test and demo readiness (Capability 7) (P0; 9a at M1, 9b at M4; track C)
**9a (early, by +8h)**
- `services/api/Dockerfile`: multi-stage uv build, non-root, one image with two commands.
- `apps/web/Dockerfile`: Next.js standalone output.
- `infra/cloudbuild.yaml`: build, push and deploy all 3 services.
- `infra/deploy.sh`:
  - Cloud Run settings: `min-instances=0` for all three services by default; `max-instances` 3 for web and api, 2 for the worker; small CPU and memory; service accounts, env vars and secrets.
  - `infra/demo-mode.sh on|off` sets `min-instances=1` on web and api for the demo window only, and back to 0 afterwards.
  - Only `web` is public. `api` accepts calls only from the web service account (BFF uses an ID token); `worker` accepts only the Pub/Sub service account.
  - Deploy the skeleton immediately.

**9b (hardening)**
- Integration tests with the Firestore and Pub/Sub emulators: the full pipeline plus the job bus.
- Playwright smoke run against the deployed URL. Load the 3 samples. Verify the golden totals in the deployed environment.
- `docs/demo-runbook.md`:
  - Demo script with timings.
  - Fallbacks: `DATA_MODE=demo_snapshot`, `JOB_BACKEND=inline`, LLM-down behaviour.
  - Reset steps and pre-demo checklist.
- Update the root README with setup, run and deploy steps.

---

## P2 stretch / cut list (in cut order if behind schedule)
1. `analytics.events` and an insights page
2. Multi-level BOM roll-up
3. Live Nexar adapter (keep DigiKey and Mouser)
4. Guided tour coach marks (keep the one-click demo seed)
5. LLM risk narrator (templates are fine)
6. Hypothesis and schemathesis suites
7. Live DigiKey and Mouser adapters (snapshot catalog only, clearly labelled)

**Never cut:** provenance on values, evidence drawer, the 4 human gates, grounding check, cloud deployment.

## Engineering standards (apply to every phase)
- Typed throughout: mypy with no untyped defs in `app/`; TS `strict`. Pydantic at every boundary.
- Layering: routers → services → domain. Domain has no I/O. Infrastructure sits behind Protocols, with in-memory implementations for tests.
- No secrets in code. No f-string queries (BigQuery query parameters only). Errors are never swallowed: degraded data becomes evidence plus a warning.
- Each module has unit tests. Coverage of at least 85% on `domain/`, `impact/`, `risk/`, `pricing/` and `ingestion/`.
- Small commits on short-lived branches merged to `main` after CI passes. Conventional commit messages.

## Prerequisites (owners: you and your team; start now)
- A dedicated GCP project on the **free-trial credits** with the Vertex AI API enabled in `us-central1`. Check that the trial end date is after judging.
- Use Gemini through **Vertex AI only**. The credit does not cover AI Studio Gemini API keys.
- Distributor API keys, which are optional and only needed for P1 live data: DigiKey (client id and secret), Mouser (search key), Nexar (client id and secret).
- `gcloud`, `uv`, `pnpm`, Node 20+, Docker installed locally.

## Verification
- **Per phase:** that phase's unit and golden tests pass in CI (`uv run pytest`, `pnpm test`).
- **M2 (API-only end to end):** `scripts/e2e_api.py` runs against the deployed api:
  - create → upload motor_controller → confirm mapping → poll job
  - assert the expected risk rule_ids and the material total for each volume
  - waive or resolve blockers → approve the EOL alternate → finalize the quote → download the XLSX
- **M3/M4 (UI end to end):** Playwright `hero-flow.spec.ts` on the Cloud Run URL. Plus a manual run of the copilot eval set; at least 8 of 10 answers must be grounded with correct citations.
- **Resilience:** rerun the hero flow three ways (`DATA_MODE=demo_snapshot`, `JOB_BACKEND=inline`, invalid Gemini model id). It must still complete, with template fallbacks shown.
- **Demo readiness:** two full rehearsals following `docs/demo-runbook.md` on the deployed URL.
- **Cost check:** after each milestone, review Billing reports by SKU. Spend should be small and mostly Vertex AI. Firestore daily reads and writes should stay under the free quotas; check them in the Firestore usage tab after an end-to-end run.
