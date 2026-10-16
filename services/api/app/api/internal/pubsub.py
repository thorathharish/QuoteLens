"""Pub/Sub push endpoint for the worker (OIDC-verified)."""

import asyncio
import base64
import binascii
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field

from app.api.deps import ContainerDep
from app.config import Settings
from app.domain.errors import UnauthenticatedError, ValidationFailedError
from app.infra.jobbus import decode_job_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)


class PubSubMessage(BaseModel):
    data: str
    message_id: str = Field(alias="messageId")
    attributes: dict[str, str] = {}


class PushEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str


async def verify_push_token(authorization: str | None, settings: Settings) -> None:
    """Fail closed: when verification is on, a valid Google-signed OIDC token for the
    configured audience and push service account is required."""
    if not settings.pubsub_verify_oidc:
        return
    if not settings.pubsub_push_audience or not settings.pubsub_push_service_account:
        logger.error("Pub/Sub OIDC verification is enabled but not configured")
        raise UnauthenticatedError("Push authentication is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthenticatedError("Missing bearer token")

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    token = authorization.removeprefix("Bearer ")
    try:
        claims: dict[str, Any] = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            token,
            google_requests.Request(),
            audience=settings.pubsub_push_audience,
        )
    except ValueError as exc:
        raise UnauthenticatedError("Invalid push token") from exc
    if (
        not claims.get("email_verified")
        or claims.get("email") != settings.pubsub_push_service_account
    ):
        raise UnauthenticatedError("Push token is not from the expected service account")


@router.post("/jobs/pubsub", status_code=204)
async def receive_job(
    envelope: PushEnvelope,
    container: ContainerDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    await verify_push_token(authorization, container.settings)
    try:
        job_id = decode_job_message(base64.b64decode(envelope.message.data, validate=True))
    except (binascii.Error, ValueError) as exc:
        # 4xx → Pub/Sub retries and eventually dead-letters the malformed message.
        raise ValidationFailedError("Malformed job message") from exc

    # Processed synchronously: Cloud Run only allocates CPU while a request is in flight.
    # Handler failures are recorded on the job and acknowledged (no retry storm).
    await container.dispatcher.dispatch(job_id)
    return Response(status_code=204)
