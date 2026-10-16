# QuoteLens backend: one image, two entrypoints (ADR-0001).
#   api:    APP_MODULE=app.main_api:app     (default)
#   worker: APP_MODULE=app.main_worker:app
# Build from the repository root (the image also carries the demo catalog and sample BOMs):
#   docker build -f services/api/Dockerfile -t quotelens-api .

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY services/api/pyproject.toml services/api/uv.lock services/api/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/api/app ./app
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY data/catalog_seed /app/data/catalog_seed
COPY data/samples /app/data/samples
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CATALOG_SEED_DIR=/app/data/catalog_seed \
    SAMPLES_DIR=/app/data/samples \
    APP_MODULE=app.main_api:app \
    PORT=8080
USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
