"""Maps every failure to the API error envelope:
`{"error": {"code", "message", "details", "request_id"}}` (api-contract.md)."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import JsonValue
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DomainError
from app.logging import request_id_var

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_FILE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def error_response(
    status: int, code: str, message: str, details: dict[str, JsonValue] | None = None
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id_var.get(),
        }
    }
    return JSONResponse(status_code=status, content=jsonable_encoder(body))


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    if exc.http_status >= 500:
        logger.error("Domain error %s: %s", exc.code, exc.message)
    return error_response(exc.http_status, exc.code, exc.message, exc.details)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors: list[JsonValue] = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"errors": errors})


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "INTERNAL" if exc.status_code >= 500 else "ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(500, "INTERNAL", "Internal server error")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
