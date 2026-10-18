"""Typed domain errors. The API layer maps each one to the error envelope and HTTP status."""

from typing import ClassVar

from pydantic import JsonValue


class DomainError(Exception):
    code: ClassVar[str] = "INTERNAL"
    http_status: ClassVar[int] = 500

    def __init__(self, message: str, details: dict[str, JsonValue] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, JsonValue] = details or {}


class ValidationFailedError(DomainError):
    code = "VALIDATION_ERROR"
    http_status = 422


class UnauthenticatedError(DomainError):
    """Only used by internal endpoints (Pub/Sub push); the demo UI has no auth."""

    code = "UNAUTHENTICATED"
    http_status = 401


class ForbiddenError(DomainError):
    """The demo role may not do this (a demo control: there is no login)."""

    code = "FORBIDDEN"
    http_status = 403


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    http_status = 404


class ConflictError(DomainError):
    code = "CONFLICT"
    http_status = 409


class InvalidStateError(DomainError):
    code = "INVALID_STATE"
    http_status = 409


class QuoteHasOpenBlockersError(DomainError):
    code = "QUOTE_HAS_OPEN_BLOCKERS"
    http_status = 409


class UnsupportedFileError(DomainError):
    code = "UNSUPPORTED_FILE"
    http_status = 415


class FileTooLargeError(DomainError):
    code = "FILE_TOO_LARGE"
    http_status = 413


class RateLimitedError(DomainError):
    code = "RATE_LIMITED"
    http_status = 429


class UpstreamUnavailableError(DomainError):
    code = "UPSTREAM_UNAVAILABLE"
    http_status = 503


class LlmUnavailableError(DomainError):
    code = "LLM_UNAVAILABLE"
    http_status = 503
