# QuoteLens: design package

An evidence-backed BOM → quotation copilot for EMS and sourcing teams.
Built for AI Builder Cup 2026, Manufacturing: Intelligent Operations & Industrial Efficiency, and deployed on Google Cloud.

| # | Deliverable | File |
|---|---|---|
| 1 | Architecture diagram and context | [architecture.md](architecture.md) |
| 2 | High-Level Design | [hld.md](hld.md) |
| 3 | Low-Level Design (incl. sample-data plan) | [lld.md](lld.md) |
| 4 | User flows (personas + first-time viewer) | [user-flows.md](user-flows.md) |
| 5 | Competitor analysis and differentiation | [competitor-analysis.md](competitor-analysis.md) |
| 6 | API contract | [api-contract.md](api-contract.md) · [openapi.yaml](openapi.yaml) |
| — | Architecture decision records | [adr/](adr/) |
| 7 | Implementation plan (phases, milestones, team tracks) | [implementation-plan.md](implementation-plan.md) |
| — | Demo runbook (walkthrough, checklist, fallbacks) | [demo-runbook.md](demo-runbook.md) |
| — | Local testing with the real distributor APIs and OpenRouter | [local-testing.md](local-testing.md) |

## Capability → design traceability
| Capability | Module | Endpoints (api-contract #) | User flow |
|---|---|---|---|
| 1. BOM upload and quick quote | Ingestion, Quotation | 5–12, 27–30 | P2, P0 |
| 2. Distributor pricing and component details | Sourcing, Pricing | 13–15 | P1 |
| 3. Explainable BOM risk | Risk engine | 16–18 | P1, P2, P4 |
| 4. Manufacturing impact | Impact engine | 4, 19–20 | P2 |
| 5. Evidence-backed conversation | Copilot | 24–26 | all |
| 6. Alternative parts | Alternatives | 21–23 | P1, P3 |
| 7. Cloud deployment and demo readiness | Infra, Demo seed, Tests | 33–35 | P0 |

## Product principles, and how they are enforced
- **Explainable, evidence-backed:** every value is a `Fact` with provenance and `evidence_ids`. Every risk carries evidence.
- **Human review:** four gates (mapping, risk review, alternate approval, quote finalize). Each decision is audited.
- **Actual vs. calculated vs. assumed vs. recommended:** the `Provenance` enum is rendered as a badge on every value.
- **No invented data:** missing data becomes `UNAVAILABLE`, never 0 or a guess. The copilot has a numeric grounding check.
- **Demo-ready:** `cache_first` data mode, pre-warmed catalog, inline job fallback, and LLM template fallback.
