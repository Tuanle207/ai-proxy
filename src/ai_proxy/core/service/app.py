"""FastAPI app factory + lifespan wiring (§4.1, §5.1, Phase 7)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from ai_proxy.core.config import Settings
from ai_proxy.core.logging_setup import configure_logging
from ai_proxy.core.provider import registry
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import configure_middleware, require_api_key
from ai_proxy.core.service.errors import register_error_handlers
from ai_proxy.core.service.routers import artifacts, events, jobs, ops, providers, tasks


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(level=settings.log_level, json=settings.log_format == "json")
    container = ServiceContainer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await container.startup()
        try:
            yield
        finally:
            await container.shutdown()

    app = FastAPI(title="AI Proxy Service", version="0.3.0.dev0", lifespan=lifespan)
    app.state.container = container
    configure_middleware(app, settings)
    register_error_handlers(app)
    app.include_router(providers.router)
    app.include_router(tasks.router)
    app.include_router(jobs.router)
    app.include_router(ops.router)
    app.include_router(events.router)
    app.include_router(artifacts.router)

    # Mount each provider's optional API router under /v1/providers/{name}.
    for name in container.provider_names():
        spec = registry.get(name)
        if spec.api_router is not None:
            app.include_router(
                spec.api_router,
                prefix=f"/v1/providers/{name}",
                dependencies=[Depends(require_api_key)],
            )
    return app


def run() -> None:
    """Console entrypoint for `ai-proxy-api` (uvicorn with the app factory)."""
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "ai_proxy.core.service.app:create_app",
        host=settings.api_host,
        port=settings.api_port,
        factory=True,
    )
