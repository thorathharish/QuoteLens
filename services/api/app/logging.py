"""Structured JSON logging compatible with Cloud Logging.

Correlation ids (`request_id`, `project_id`, `job_id`) live in context variables so
every log line emitted while handling a request or job carries them automatically.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
project_id_var: ContextVar[str | None] = ContextVar("project_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)

_CONTEXT_VARS = {
    "request_id": request_id_var,
    "project_id": project_id_var,
    "job_id": job_id_var,
}


class JsonFormatter(logging.Formatter):
    """Emits one JSON object per line using Cloud Logging's `severity`/`message` keys."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
        }
        for key, var in _CONTEXT_VARS.items():
            value = var.get()
            if value is not None:
                entry[key] = value
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            entry.update(extra)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Uvicorn's access log duplicates our request logging and is noisy (Logging free tier).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
