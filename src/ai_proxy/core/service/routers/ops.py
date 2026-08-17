"""Operations endpoints: health, readiness, accounts, and stats (§3.6, S-17, S-18)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ai_proxy.core.browser.doctor import camoufox_status
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.service.schemas import AccountStatusResponse, StatsResponse

router = APIRouter(tags=["ops"])


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", dependencies=[Depends(require_api_key)])
async def readyz(request: Request) -> JSONResponse:
    container = _container(request)
    checks: dict[str, bool] = {}

    try:
        await container.db.fetch_val("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False

    installed, _ = camoufox_status()
    checks["camoufox"] = installed

    checks["usable_accounts"] = any(
        runtime.accounts.get_available() for runtime in container.runtimes.values()
    )

    ready = all(checks.values())
    status_code = 200 if ready else 503
    content = {"status": "ready" if ready else "not_ready", "checks": checks}
    return JSONResponse(status_code=status_code, content=content)


@router.get(
    "/v1/accounts",
    response_model=list[AccountStatusResponse],
    dependencies=[Depends(require_api_key)],
)
async def list_accounts(
    request: Request, provider: str | None = None
) -> list[AccountStatusResponse]:
    container = _container(request)
    runtimes = (
        [container.provider(provider)]
        if provider is not None
        else list(container.runtimes.values())
    )
    response: list[AccountStatusResponse] = []
    for runtime in runtimes:
        snapshot = runtime.pool.snapshot()
        for account in runtime.accounts.list_accounts():
            response.append(
                AccountStatusResponse(
                    email=account.email,
                    status=account.status.value,
                    in_flight=snapshot.per_account_in_flight.get(account.email, 0),
                    limit=snapshot.per_account_limit,
                    success_count=account.success_count,
                    fail_count=account.fail_count,
                    cooldown_until=account.cooldown_until,
                    last_used_at=account.last_used_at,
                )
            )
    return response


@router.get("/v1/stats", response_model=StatsResponse, dependencies=[Depends(require_api_key)])
async def stats(request: Request, provider: str | None = None) -> StatsResponse:
    container = _container(request)
    counts = await container.jobs.count_by_status(provider=provider)
    engine_stats = await container.engine.stats_payload()
    images_total, bytes_total = await container.artifacts.stats()
    return StatsResponse(
        queued=int(engine_stats["queued"]),
        running=int(engine_stats["running"]),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        canceled=counts.get("canceled", 0),
        total_slots=int(engine_stats["total_slots"]),
        free_slots=int(engine_stats["free_slots"]),
        throughput_jobs_per_hour=engine_stats["throughput_jobs_per_hour"],
        avg_duration_seconds=engine_stats["avg_duration_seconds"],
        eta_seconds=engine_stats["eta_seconds"],
        images_total=images_total,
        bytes_total=bytes_total,
    )
