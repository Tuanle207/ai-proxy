"""ProviderRuntime: one provider's fully-wired runtime, built by the service container."""

from __future__ import annotations

from dataclasses import dataclass

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.base import BrowserBackend
from ai_proxy.core.config import ProviderSettings
from ai_proxy.core.provider.adapter import ProviderAdapter
from ai_proxy.core.provider.auth import AuthHandler
from ai_proxy.core.provider.spec import ProviderSpec
from ai_proxy.core.rotation.pool import AccountSlotPool


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
