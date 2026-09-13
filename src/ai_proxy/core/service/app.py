"""FastAPI app factory + lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_proxy.core.config import Settings
from ai_proxy.core.logging_setup import configure_logging
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import configure_middleware
from ai_proxy.core.service.errors import register_error_handlers
from ai_proxy.core.service.routers import chat, download, images, ops, providers, upload, media


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
    app.include_router(ops.router)
    app.include_router(chat.router)
    app.include_router(images.router)
    app.include_router(upload.router)
    app.include_router(media.router)
    app.include_router(download.router)
    return app


def run() -> None:
    import uvicorn

    settings = Settings()
    print(f"Starting AI Proxy service on {settings.api_host}:{settings.api_port}...")
    uvicorn.run(
        "ai_proxy.core.service.app:create_app",
        host=settings.api_host,
        port=settings.api_port,
        factory=True,
    )


if __name__ == "__main__":
    run()