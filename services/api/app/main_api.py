"""Public API service entrypoint: `uvicorn app.main_api:app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routers import (
    alternatives,
    bom,
    copilot,
    insights,
    jobs,
    lines,
    projects,
    risks,
    sourcing,
)
from app.app_factory import create_base_app
from app.config import Settings
from app.container import Container

API_PREFIX = "/api/v1"


def _configure(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Demo-Role", "X-Request-Id", "Idempotency-Key"],
        expose_headers=["X-Request-Id"],
    )
    routers = (
        projects.router,
        bom.router,
        jobs.router,
        lines.router,
        sourcing.router,
        insights.router,
        risks.router,
        alternatives.router,
        copilot.router,
    )
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)


def create_app(container: Container | None = None) -> FastAPI:
    return create_base_app("QuoteLens API", container, _configure)


app = create_app()
