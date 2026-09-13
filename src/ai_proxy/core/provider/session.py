"""ProviderSession and ProviderRuntimeDeps: the dependency envelope handed to an adapter."""

from __future__ import annotations
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import structlog
from playwright.async_api import Page

from ai_proxy.core.browser.base import BrowserBackend
from ai_proxy.core.config import ProviderSettings
from ai_proxy.core.models import Account, WorkspaceRef
from ai_proxy.core.paths import DataPaths

WorkspaceCreated = Callable[[WorkspaceRef], Awaitable[None]]


@dataclass
class ProviderSession:
    account: Account
    page: Page | None
    paths: DataPaths
    output_dir: Path
    settings: ProviderSettings
    on_workspace_created: WorkspaceCreated = lambda _: None  # no-op default


@dataclass
class ProviderRuntimeDeps:
    settings: ProviderSettings
    paths: DataPaths
    backend: BrowserBackend
    logger: structlog.stdlib.BoundLogger
