"""Public library API: `AIProxyClient`, a provider-parametrized facade over the registry."""

from __future__ import annotations

import asyncio
from typing import Any

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.browser.camoufox_backend import CamoufoxBackend
from ai_proxy.core.config import Settings
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import Account, TaskKind, TaskRequest, TaskResult
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.session import ProviderRuntimeDeps, ProviderSession
from ai_proxy.core.rotation.limiter import ConcurrencyLimiter
from ai_proxy.core.rotation.scheduler import JobScheduler
from ai_proxy.core.rotation.strategy import RoundRobinStrategy
from ai_proxy.core.service.storage import LocalStorage

_DEFAULT_PROVIDER = "google_flow"


async def _noop(*args: Any, **kwargs: Any) -> None:
    return None


class AIProxyClient:
    """Async-first public API. See `generate_image_sync` for a blocking facade."""

    def __init__(self, settings: Settings | None = None, provider: str = _DEFAULT_PROVIDER):
        self.settings = settings or Settings()
        self.provider = provider
        registry.discover()
        self._spec = registry.get(provider)
        self._paths = self.settings.paths
        self._backend = CamoufoxBackend(self._paths, provider)
        self._storage = LocalStorage(self._paths.outputs_dir)
        self._accounts = AccountManager(self._paths, provider)
        self._deps = ProviderRuntimeDeps(
            settings=self._spec.settings_model(),
            paths=self._paths,
            backend=self._backend,
            storage=self._storage,
            logger=get_logger(),
        )
        self._adapter = self._spec.build_adapter(self._deps)
        self._scheduler = JobScheduler(
            self._accounts,
            RoundRobinStrategy(),
            ConcurrencyLimiter(per_account=self.settings.per_account_concurrency),
            max_retries=self.settings.max_retries,
        )

    async def generate_image(self, prompt_text: str, **opts: Any) -> TaskResult:
        """Generate image(s) from a prompt, rotating across available accounts."""
        return await self.run(self._build_task_request(prompt_text, **opts))

    async def run(self, request: TaskRequest) -> TaskResult:
        """Run a pre-built task request across the provider's accounts."""

        async def job(account: Account) -> TaskResult:
            return await self._run(request, account)

        return await self._scheduler.run(job)

    def run_sync(self, request: TaskRequest) -> TaskResult:
        return asyncio.run(self.run(request))

    async def generate_batch(self, prompts: list[str], **opts: Any) -> list[TaskResult]:
        """Generate images for multiple prompts concurrently (rotation applies per-prompt)."""
        return await asyncio.gather(*(self.generate_image(p, **opts) for p in prompts))

    def generate_image_sync(self, prompt_text: str, **opts: Any) -> TaskResult:
        return asyncio.run(self.generate_image(prompt_text, **opts))

    def generate_batch_sync(self, prompts: list[str], **opts: Any) -> list[TaskResult]:
        return asyncio.run(self.generate_batch(prompts, **opts))

    def _build_task_request(self, prompt_text: str, **opts: Any) -> TaskRequest:
        task_fields = {"count", "timeout", "inputs"}
        fields = {k: opts.pop(k) for k in task_fields if k in opts}
        if "reference_images" in opts:  # legacy kwarg from the pre-refactor API
            fields["inputs"] = opts.pop("reference_images")
        params = {k: v for k, v in opts.items() if v is not None}
        return TaskRequest(
            provider=self.provider,
            kind=TaskKind.IMAGE,
            prompt=prompt_text,
            params=params,
            **fields,
        )

    async def _run(self, request: TaskRequest, account: Account) -> TaskResult:
        output_dir = self._paths.outputs_dir
        if self._spec.capabilities.requires_browser:
            async with self._backend.browser_context(
                account, headless=self.settings.headless
            ) as context:
                page = await context.new_page()
                try:
                    session = ProviderSession(
                        account=account,
                        page=page,
                        http=None,
                        paths=self._paths,
                        output_dir=output_dir,
                        settings=self._deps.settings,
                        emit=_noop,
                        on_workspace_created=_noop,
                    )
                    result = await self._adapter.execute(session, request)
                finally:
                    await page.close()
        else:
            session = ProviderSession(
                account=account,
                page=None,
                http=None,
                paths=self._paths,
                output_dir=output_dir,
                settings=self._deps.settings,
                emit=_noop,
                on_workspace_created=_noop,
            )
            result = await self._adapter.execute(session, request)
        await self._adapter.cleanup(session, result.workspace_ref)
        return result
