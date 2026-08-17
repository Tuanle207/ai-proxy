"""Exception handlers → the single error envelope (§3), with sanitized messages (§6.5)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ai_proxy.core.errors import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    AIProxyError,
    NoAvailableAccountError,
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _sanitize(message: str) -> str:
    return _EMAIL_RE.sub("***", message)


def error_response(
    code: str, message: str, status_code: int, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": _sanitize(message), "details": details or {}}},
    )


_AI_PROXY_ERROR_STATUS: dict[type[AIProxyError], int] = {
    AccountNotFoundError: 404,
    AccountAlreadyExistsError: 409,
    NoAvailableAccountError: 503,
}

_HTTP_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AIProxyError)
    async def _ai_proxy_error(request: Request, exc: AIProxyError) -> JSONResponse:
        status = _AI_PROXY_ERROR_STATUS.get(type(exc), 500)
        return error_response(type(exc).__name__, str(exc), status)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(
            exc.status_code,
            "http_error" if exc.status_code < 500 else "internal_error",
        )
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return error_response(code, detail, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            "validation_error", "request validation failed", 422, {"errors": exc.errors()}
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return error_response("internal_error", "internal server error", 500)
