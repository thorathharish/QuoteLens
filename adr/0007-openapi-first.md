# ADR-0007: OpenAPI as the contract source of truth
- **Status:** Accepted
- **Context:** Separate frontend and backend, built quickly, where drift is likely.
- **Decision:** FastAPI Pydantic DTOs generate `openapi.yaml`. The frontend generates types with `openapi-typescript`, and CI runs schemathesis contract tests. `docs/openapi.yaml` is the reviewed draft until code exists.
- **Consequences:** One source of truth, and breaking changes show up in CI.
