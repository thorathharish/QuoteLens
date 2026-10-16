"""Job worker entrypoint (Pub/Sub push target): `uvicorn app.main_worker:app`."""

from fastapi import FastAPI

from app.api.internal import pubsub
from app.app_factory import create_base_app
from app.config import Settings
from app.container import Container


def _configure(app: FastAPI, _: Settings) -> None:
    app.include_router(pubsub.router)


def create_app(container: Container | None = None) -> FastAPI:
    return create_base_app("QuoteLens Worker", container, _configure)


app = create_app()
