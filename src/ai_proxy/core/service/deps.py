"""Dependencies: container accessor, API-key guard, and middleware (§6.5, §6.9)."""

from __future__ import annotations

import secrets
import uuid
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

from ai_proxy.core.config import Settings
from ai_proxy.core.service.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


async def require_api_key(request: Request) -> None:
    container = cast(ServiceContainer, request.app.state.container)
    provided = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(provided, container.api_key):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def configure_middleware(app: FastAPI, settings: Settings) -> None:
    origins = settings.cors_origins
    if "*" in origins:
        raise ValueError("cors_origins may not contain '*' — use an explicit allowlist")
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestIDMiddleware)
