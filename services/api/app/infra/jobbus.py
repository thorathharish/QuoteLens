"""Job buses (ADR-0006): Pub/Sub for deployed environments, in-process for local/tests."""

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def encode_job_message(job_id: str) -> bytes:
    """Messages carry only the job id: tiny payloads keep Pub/Sub inside the free tier."""
    return json.dumps({"job_id": job_id}).encode()


def decode_job_message(data: bytes) -> str:
    payload = json.loads(data)
    job_id = payload.get("job_id") if isinstance(payload, dict) else None
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("Job message has no job_id")
    return job_id


class InlineJobBus:
    """Runs jobs as asyncio tasks in the current process.

    Not for Cloud Run with request-based CPU: work after the response is throttled.
    """

    def __init__(self, run: Callable[[str], Coroutine[Any, Any, object]]) -> None:
        self._run = run
        self._tasks: set[asyncio.Task[object]] = set()

    async def publish(self, job_id: str) -> None:
        task: asyncio.Task[object] = asyncio.create_task(self._run(job_id), name=f"job:{job_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for in-flight jobs (tests, graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


class PubSubJobBus:
    def __init__(self, project: str, topic: str) -> None:
        # Imported lazily: only needed when deployed.
        from google.cloud.pubsub_v1 import PublisherClient

        self._publisher = PublisherClient()
        self._topic_path = self._publisher.topic_path(project, topic)

    async def publish(self, job_id: str) -> None:
        future = self._publisher.publish(self._topic_path, data=encode_job_message(job_id))
        message_id = await asyncio.to_thread(future.result, timeout=30)
        logger.info("Published job", extra={"fields": {"job": job_id, "message_id": message_id}})

    async def drain(self) -> None:
        return None
