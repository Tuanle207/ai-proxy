"""ProviderSession and ProviderRuntimeDeps: the dependency envelope handed to an adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog
from playwright.async_api import Page

from ai_proxy.core.browser.base import BrowserBackend
from ai_proxy.core.config import ProviderSettings
from ai_proxy.core.models import Account, WorkspaceRef
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.service.storage import StorageBackend

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
WorkspaceCreated = Callable[[WorkspaceRef], Awaitable[None]]


@dataclass
class ProviderSession:
    """A live, per-job handle core builds and hands to `ProviderAdapter.execute`.

    `page` is set only when the provider's capabilities declare `requires_browser`; otherwise an
    HTTP runtime provides `http` instead.
    """

    account: Account
    page: Page | None
    http: httpx.AsyncClient | None
    paths: DataPaths
    output_dir: Path
    settings: ProviderSettings
    emit: Emit
    on_workspace_created: WorkspaceCreated


@dataclass
class ProviderRuntimeDeps:
    """Long-lived, provider-scoped dependencies injected by core when building a provider."""

    settings: ProviderSettings
    paths: DataPaths
    backend: BrowserBackend
    storage: StorageBackend
    logger: structlog.stdlib.BoundLogger
