"""Operations endpoints: health and readiness probes."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key

router = APIRouter(tags=["ops"])


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", dependencies=[Depends(require_api_key)])
async def readyz(request: Request) -> JSONResponse:
    container = _container(request)
    checks: dict[str, bool] = {
        "usable_accounts": any(
            runtime.accounts.get_available() for runtime in container.runtimes.values()
        ),
    }
    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
