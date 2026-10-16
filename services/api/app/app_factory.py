"""Shared FastAPI app construction for the `api` and `worker` entrypoints."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.middleware import RequestIdMiddleware
from app.api.v1.routers import health
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.logging import configure_logging


def create_base_app(
    title: str,
    container: Container | None = None,
    configure: Callable[[FastAPI, Settings], None] | None = None,
) -> FastAPI:
    """`container` defaults to one built from environment settings; tests inject their own.
    Settings are always read from the container so there is a single source of truth."""
    resolved = container or build_container(get_settings())
    settings = resolved.settings
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved.job_bus.drain()

    app = FastAPI(
        title=title,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
    )
    app.state.container = resolved
    install_error_handlers(app)
    app.include_router(health.router)
    if configure is not None:
        configure(app, settings)
    app.add_middleware(RequestIdMiddleware)
    return app
