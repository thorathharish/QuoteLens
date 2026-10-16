# QuoteLens API and worker

FastAPI backend: one codebase, two entrypoints (ADR-0001).

| Entrypoint | Role |
|---|---|
| `app.main_api:app` | Public REST API (`/api/v1`, `/healthz`, `/readyz`) |
| `app.main_worker:app` | Pub/Sub push target that runs background jobs (`/internal/jobs/pubsub`) |

## Layout
```
app/
  domain/        pure models: Fact/Evidence provenance, enums, errors, ids (no I/O)
  infra/         adapters: document store (memory | Firestore), job bus (inline | Pub/Sub)
  jobs/          job lifecycle: enqueue, dispatch, progress, idempotent redelivery
  api/           HTTP layer: routers, error envelope, request-id middleware, deps
  container.py   composition root (settings → store, repositories, job bus)
```

## Develop
```bash
uv sync                      # Python 3.12 venv + deps
cp .env.example .env         # defaults run fully offline (memory store, inline jobs)
uv run uvicorn app.main_api:app --reload --port 8080
uv run uvicorn app.main_worker:app --reload --port 8081

uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest --cov
```

Firestore integration tests run when the emulator is up:
```bash
gcloud emulators firestore start --host-port=localhost:8681
FIRESTORE_EMULATOR_HOST=localhost:8681 uv run pytest -m firestore
```
