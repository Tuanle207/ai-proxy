"""Provider runtime construction without HTTP or API-key ownership."""

from __future__ import annotations

import asyncio

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.camoufox_backend import CamoufoxBackend
from ai_proxy.core.config import Settings
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.runtime import ProviderRuntime
from ai_proxy.core.provider.session import ProviderRuntimeDeps
from ai_proxy.core.rotation.pool import AccountSlotPool
from ai_proxy.core.rotation.strategy import RoundRobinStrategy

_log = get_logger()


class ProviderRuntimeContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.paths = settings.paths
        registry.discover()
        self.runtimes = self._build_runtimes()

    def _build_runtimes(self) -> dict[str, ProviderRuntime]:
        global_semaphore = asyncio.Semaphore(self.settings.max_concurrent_browsers)
        runtimes: dict[str, ProviderRuntime] = {}
        for name in registry.names():
            spec = registry.get(name)
            provider_settings = spec.settings_model(**self.settings.provider_settings(name))
            accounts = AccountManager(self.paths, name)
            backend = CamoufoxBackend(
                self.paths,
                name,
                idle_ttl_seconds=self.settings.browser_idle_ttl_seconds,
                max_tabs_per_session=getattr(provider_settings, "max_tabs_per_session", None) or 1,
                window_size=(self.settings.browser_window_width, self.settings.browser_window_height)
                if self.settings.browser_window_width and self.settings.browser_window_height
                else None,
            )
            pool = AccountSlotPool(
                accounts,
                RoundRobinStrategy(),
                per_account_limit=getattr(provider_settings, "per_account_concurrency", None)
                or self.settings.per_account_concurrency,
                max_concurrent_browsers=self.settings.max_concurrent_browsers,
                global_semaphore=global_semaphore,
            )
            deps = ProviderRuntimeDeps(provider_settings, self.paths, backend, _log)
            runtimes[name] = ProviderRuntime(spec, provider_settings, accounts, pool, backend, spec.build_adapter(deps), spec.build_auth(deps))
        return runtimes

    def provider(self, name: str) -> ProviderRuntime:
        return self.runtimes[name]

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        for runtime in self.runtimes.values():
            await runtime.backend.close_all()
