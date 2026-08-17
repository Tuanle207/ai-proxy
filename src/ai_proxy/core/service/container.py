"""ServiceContainer: the process-wide singletons wired together (§4.2, Phase 7.1).

Exactly one instance is built by the app factory and shared across the process. Core owns the
SQLite connection, repositories, event bus, storage, runner and engine; each registered provider
gets a `ProviderRuntime` (its own accounts, pool, backend, adapter, auth) built from the registry.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import stat
from pathlib import Path

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.camoufox_backend import CamoufoxBackend
from ai_proxy.core.config import Settings
from ai_proxy.core.db.artifacts_repo import ArtifactsRepo
from ai_proxy.core.db.engine import Database
from ai_proxy.core.db.events_repo import EventsRepo
from ai_proxy.core.db.jobs_repo import JobRecord, JobsRepo
from ai_proxy.core.db.migrations import run_core_migrations, run_migrations
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.runtime import ProviderRuntime
from ai_proxy.core.provider.session import ProviderRuntimeDeps
from ai_proxy.core.rotation.pool import AccountSlotPool
from ai_proxy.core.rotation.strategy import RoundRobinStrategy
from ai_proxy.core.service.backfill import backfill_images
from ai_proxy.core.service.storage import LocalStorage
from ai_proxy.core.worker.bus import EventBus
from ai_proxy.core.worker.engine import WorkerEngine
from ai_proxy.core.worker.recovery import recover_orphaned_running
from ai_proxy.core.worker.runner import TaskRunner

_log = get_logger()


class ServiceContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.paths = settings.paths
        self.db = Database(self._db_path())
        self.jobs = JobsRepo(self.db)
        self.artifacts = ArtifactsRepo(self.db)
        self.events = EventsRepo(self.db)
        self.bus = EventBus(self.events, maxsize=settings.sse_queue_maxsize)
        self.storage = LocalStorage(self.paths.outputs_dir)
        registry.discover()
        self.runtimes = self._build_runtimes(settings)
        self.runner = TaskRunner(
            settings, self.paths, self.storage, self.artifacts, self.jobs, self.bus
        )
        self.engine = WorkerEngine(
            settings,
            self.paths,
            self.jobs,
            self.artifacts,
            self.bus,
            self.storage,
            self.runner,
            self.runtimes,
        )
        self.api_key = self._resolve_api_key()

    def _build_runtimes(self, settings: Settings) -> dict[str, ProviderRuntime]:
        global_semaphore = asyncio.Semaphore(settings.max_concurrent_browsers)
        runtimes: dict[str, ProviderRuntime] = {}
        for name in registry.names():
            spec = registry.get(name)
            provider_settings = spec.settings_model()
            accounts = AccountManager(self.paths, name)
            backend = CamoufoxBackend(self.paths, name)
            pool = AccountSlotPool(
                accounts,
                RoundRobinStrategy(),
                per_account_limit=settings.per_account_concurrency,
                max_concurrent_browsers=settings.max_concurrent_browsers,
                global_semaphore=global_semaphore,
            )
            deps = ProviderRuntimeDeps(
                settings=provider_settings,
                paths=self.paths,
                backend=backend,
                storage=self.storage,
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

    def _db_path(self) -> Path:
        return Path(self.settings.db_path) if self.settings.db_path else self.paths.db_file

    def _resolve_api_key(self) -> str:
        """Resolve the API key per §6.9: env/config → `data/api_key` → generate + persist."""
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
            pass  # Windows does not honor POSIX modes
        _log.warning("generated default API key — set AI_PROXY_API_KEY in production")
        return key

    async def _on_orphan(self, job: JobRecord) -> None:
        runtime = self.runtimes.get(job.provider)
        if runtime is not None and runtime.spec.on_orphan is not None:
            await runtime.spec.on_orphan(self.db, job)

    async def startup(self) -> None:
        await self.db.connect()
        await run_core_migrations(self.db)
        for name, runtime in self.runtimes.items():
            await run_migrations(self.db, name, runtime.spec.migrations)
        await recover_orphaned_running(self.jobs, on_orphan=self._on_orphan)
        await backfill_images(self.artifacts, self.storage, self.paths)
        await self.engine.start()

    async def shutdown(self) -> None:
        await self.engine.shutdown()
        await self.db.close()
