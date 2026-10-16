# ADR-0001: Modular monolith deployed as three Cloud Run services
- **Status:** Accepted (2026-10-16)
- **Context:** Small team, about 2 days to build, and the demo must be reliable. The domain has clear modules (ingestion, sourcing, risk, impact, alternatives, copilot, quotation).
- **Decision:** One Python codebase with strict module boundaries (`app/<module>`; domain layer has no I/O). It ships as one image with two entrypoints (`api`, `worker`), plus a separate Next.js `web` service.
- **Consequences:** Simple build and deploy, shared models, no network hops between modules. A module can be extracted later if needed. Module discipline is enforced by import rules (ruff/import-linter).
