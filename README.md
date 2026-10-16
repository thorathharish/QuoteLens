# QuoteLens

**Evidence-backed BOM → quotation copilot for electronics manufacturing (EMS) and sourcing teams.**

Built for **AI Builder Cup 2026**, Manufacturing: Intelligent Operations & Industrial Efficiency. Deployed on **Google Cloud**.

> **Status:** Design approved; implementation starting. See the [implementation plan](docs/implementation-plan.md).

---

## The problem
Turning a customer BOM/RFQ into a quote takes days of manual work:
- Cleaning messy spreadsheets
- Checking every part across distributors
- Spotting EOL, long-lead or single-source parts
- Working out MOQ, scrap and excess cost
- Hunting for alternates

The result is hard to defend, because nobody can easily show *where each number came from*.

## What QuoteLens does
Upload a BOM and get a **defensible quote**. Every value is labelled **Actual · Calculated · Assumed · Unavailable · Recommended** and links to its evidence.

| # | Capability | What you get |
|---|---|---|
| 1 | **BOM upload and quick quote** | AI-assisted column mapping, normalization, validation, instant first-pass quote, inline corrections |
| 2 | **Distributor pricing and component details** | Multi-distributor offers (stock, MOQ, lead time, price breaks, lifecycle) with the source and freshness of each value |
| 3 | **Explainable BOM risk** | EOL/NRND, single source, lead time, price outliers, data issues. Each risk explains *why*, with evidence, and can be resolved or waived. |
| 4 | **Manufacturing impact** | MOQ, scrap/attrition, excess/shortage and price-break effects per build volume, with a calculation trace |
| 5 | **Evidence-backed copilot** | Chat over the project data. Answers cite their sources, and numbers are checked against the data. |
| 6 | **Alternative parts** | Parameter-by-parameter comparison, fit class and explanation. A person must approve before any swap. |
| 7 | **Cloud deployment and demo readiness** | Runs end to end on Cloud Run, with sample BOMs and a guided demo mode |

**Demo journey:** upload BOM → pricing → risks → manufacturing impact → alternatives → copilot → finalized quote

## Architecture at a glance
```mermaid
flowchart LR
  user([User]) --> web["Next.js<br/>(Cloud Run)"]
  web --> api["FastAPI + LangGraph<br/>(Cloud Run)"]
  api --> ps[[Pub/Sub]] --> worker["Worker<br/>(Cloud Run)"]
  api & worker --> fs[(Firestore)]
  api & worker --> bq[(BigQuery<br/>catalog + cache)]
  api & worker --> gcs[(Cloud Storage)]
  api & worker --> vx{{Gemini on Vertex AI}}
  worker --> dist[Nexar · DigiKey · Mouser]
```
**Design principle:** a deterministic core with the LLM at the edges. Plain, tested code calculates every price, risk and impact number. Gemini maps columns, explains results, investigates alternates and powers the copilot. It never produces the financial numbers.

## Tech stack
| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router, TypeScript), Tailwind, shadcn/ui, TanStack Query/Table |
| Backend | Python 3.12, FastAPI, Pydantic v2, LangChain + LangGraph |
| AI | Gemini on Vertex AI |
| Data | Firestore (app state), BigQuery (component catalog, price cache, analytics), Cloud Storage (files) |
| Async | Pub/Sub → Cloud Run worker (inline fallback) |
| Ops | Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Cloud Logging |

## Documentation
Everything is in [`docs/`](docs/README.md):

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Context, system and module diagrams, pipeline sequence |
| [High-Level Design](docs/hld.md) | Fact/Evidence model, modules, state machine, NFRs, deployment |
| [Low-Level Design](docs/lld.md) | Repo layout, data models, storage schemas, algorithms, risk rules, testing, sample data |
| [User Flows](docs/user-flows.md) | First-time viewer plus 4 personas |
| [Competitor Analysis](docs/competitor-analysis.md) | Market landscape and differentiation |
| [API Contract](docs/api-contract.md) · [OpenAPI](docs/openapi.yaml) | 35 endpoints, error model, SSE copilot stream |
| [ADRs](docs/adr/) | Architecture decision records |
| [Implementation Plan](docs/implementation-plan.md) | Phases 0–9, milestones, team tracks, cut list, verification |

## Repository layout (planned)
```
apps/web/          Next.js frontend
services/api/      FastAPI api + worker (shared codebase)
data/samples/      Sample BOMs + golden expected outputs
data/catalog_seed/ Curated component catalog for BigQuery
infra/             Cloud Build, deploy scripts, schemas
docs/              Design documentation
```

## Getting started
Setup and deployment instructions will be added with the implementation.

## Team
Team **miscellaneous**, AI Builder Cup 2026.
