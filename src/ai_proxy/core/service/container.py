"""Service container: builds and wires provider runtimes."""

from __future__ import annotations

import asyncio
import os
import secrets
import stat

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


class ServiceContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.paths = settings.paths
        registry.discover()
        self.runtimes = self._build_runtimes(settings)
        self.api_key = self._resolve_api_key()

    def _build_runtimes(self, settings: Settings) -> dict[str, ProviderRuntime]:
        global_semaphore = asyncio.Semaphore(settings.max_concurrent_browsers)
        runtimes: dict[str, ProviderRuntime] = {}
        for name in registry.names():
            spec = registry.get(name)
            provider_settings = spec.settings_model()
            accounts = AccountManager(self.paths, name)
            max_tabs_per_session = getattr(provider_settings, "max_tabs_per_session", None) or 1
            window_size = None
            if settings.browser_window_width and settings.browser_window_height:
                window_size = (settings.browser_window_width, settings.browser_window_height)
            backend = CamoufoxBackend(
                self.paths,
                name,
                idle_ttl_seconds=settings.browser_idle_ttl_seconds,
                max_tabs_per_session=max_tabs_per_session,
                window_size=window_size,
            )
            per_account_limit = getattr(provider_settings, "per_account_concurrency", None)
            if per_account_limit is None:
                per_account_limit = settings.per_account_concurrency
            pool = AccountSlotPool(
                accounts,
                RoundRobinStrategy(),
                per_account_limit=per_account_limit,
                max_concurrent_browsers=settings.max_concurrent_browsers,
                global_semaphore=global_semaphore,
            )
            deps = ProviderRuntimeDeps(
                settings=provider_settings,
                paths=self.paths,
                backend=backend,
                logger=_log,
            )
            runtimes[name] = ProviderRuntime(
                spec=spec,
                settings=provider_settings,
                accounts=accounts,
                pool=pool,
                backend=backend,
                adapter=spec.build_adapter(deps),
                auth=spec.build_auth(deps),
            )
        return runtimes

    def provider(self, name: str) -> ProviderRuntime:
        return self.runtimes[name]

    def provider_names(self) -> list[str]:
        return sorted(self.runtimes)

    def _resolve_api_key(self) -> str:
        if self.settings.api_key:
            return self.settings.api_key
        key_file = self.paths.api_key_file
        if key_file.is_file():
            key = key_file.read_text(encoding="utf-8").strip()
            if key:
                return key
        key = secrets.token_urlsafe(32)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key, encoding="utf-8")
        try:
            os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        _log.warning("generated default API key — set AI_PROXY_API_KEY in production")
        return key

    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        for runtime in self.runtimes.values():
            await runtime.backend.close_all()
