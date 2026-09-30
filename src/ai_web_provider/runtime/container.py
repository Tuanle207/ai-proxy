"""Provider runtime construction without HTTP or API-key ownership."""

from __future__ import annotations

import asyncio

from ai_web_provider.core.accounts.manager import AccountManager
from ai_web_provider.core.browser.ungoogled_chromium_backend import UngoogledChromiumBackend
from ai_web_provider.core.config import Settings
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.core.provider import registry
from ai_web_provider.core.provider.runtime import ProviderRuntime
from ai_web_provider.core.provider.session import ProviderRuntimeDeps
from ai_web_provider.core.rotation.pool import AccountSlotPool
from ai_web_provider.core.rotation.strategy import RoundRobinStrategy
from ai_web_provider.runtime.ungoogled_chromium import UngoogledChromiumRuntimeManager

_log = get_logger()


class ProviderRuntimeContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.paths = settings.paths
        registry.discover()
        self._browser = UngoogledChromiumRuntimeManager(self.paths, settings.browser)
        self.runtimes = self._build_runtimes()
        self._lifecycle_lock = asyncio.Lock()
        self._started = False

    def _build_runtimes(self) -> dict[str, ProviderRuntime]:
        global_semaphore = asyncio.Semaphore(self.settings.max_concurrent_jobs)
        runtimes: dict[str, ProviderRuntime] = {}
        for name in registry.names():
            spec = registry.get(name)
            provider_settings = spec.settings_model(**self.settings.provider_settings(name))
            accounts = AccountManager(self.paths, name)
            backend = UngoogledChromiumBackend(name, self._browser)
            per_account_limit = self.settings.per_account_concurrency
            per_account_limits = None
            if name == "google_flow":
                projects_by_account = getattr(provider_settings, "projects_by_account", {})
                per_account_limits = {
                    email: min(per_account_limit, len(projects))
                    for email, projects in projects_by_account.items()
                }
            pool = AccountSlotPool(
                accounts,
                RoundRobinStrategy(),
                per_account_limit=per_account_limit,
                per_account_limits=per_account_limits,
                max_concurrent_jobs=self.settings.max_concurrent_jobs,
                global_semaphore=global_semaphore,
            )
            deps = ProviderRuntimeDeps(provider_settings, self.paths, backend, _log)
            runtimes[name] = ProviderRuntime(
                spec,
                provider_settings,
                accounts,
                pool,
                backend,
                spec.build_adapter(deps),
                spec.build_auth(deps),
            )
        return runtimes

    def provider(self, name: str) -> ProviderRuntime:
        return self.runtimes[name]

    async def startup(self) -> None:
        async with self._lifecycle_lock:
            if self._started:
                return
            await self._browser.startup()
            self._started = True

    async def shutdown(self) -> None:
        async with self._lifecycle_lock:
            for runtime in self.runtimes.values():
                await runtime.backend.close_all()
            await self._browser.shutdown()
            self._started = False
