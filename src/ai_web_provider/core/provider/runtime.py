"""ProviderRuntime: one provider's fully-wired runtime, built by the service container."""

from __future__ import annotations

from dataclasses import dataclass

from ai_web_provider.core.accounts.manager import AccountManager
from ai_web_provider.core.browser.base import BrowserBackend
from ai_web_provider.core.config import ProviderSettings
from ai_web_provider.core.provider.adapter import ProviderAdapter
from ai_web_provider.core.provider.auth import AuthHandler
from ai_web_provider.core.provider.spec import ProviderSpec
from ai_web_provider.core.rotation.pool import AccountSlotPool


@dataclass
class ProviderRuntime:
    """Long-lived, provider-scoped wiring. Core keeps one per registered provider."""

    spec: ProviderSpec
    settings: ProviderSettings
    accounts: AccountManager
    pool: AccountSlotPool
    backend: BrowserBackend
    adapter: ProviderAdapter
    auth: AuthHandler
