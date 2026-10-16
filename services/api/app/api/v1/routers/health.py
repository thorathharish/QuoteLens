"""Liveness and readiness probes."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ContainerDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_DEP_TIMEOUT_SECONDS = 3.0


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    deps: dict[str, Literal["ok", "error"]]


@router.get("/healthz", response_model=Liveness)
async def healthz() -> Liveness:
    return Liveness()


@router.get("/readyz", response_model=Readiness)
async def readyz(container: ContainerDep) -> Readiness:
    deps: dict[str, Literal["ok", "error"]] = {}
    try:
        await asyncio.wait_for(container.repos.store.ping(), _DEP_TIMEOUT_SECONDS)
        deps["store"] = "ok"
    except Exception:
        logger.exception("Readiness check failed for store")
        deps["store"] = "error"
    status: Literal["ok", "degraded"] = (
        "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    )
    return Readiness(status=status, deps=deps)
