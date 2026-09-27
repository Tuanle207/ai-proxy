"""Single owner of browser execution, retries, and account effects."""

from __future__ import annotations

from datetime import timedelta

from ai_web_provider.core.errors import NoAvailableAccountError
from ai_web_provider.core.failure import AccountEffect, default_classify_failure
from ai_web_provider.core.models import AccountStatus, TaskRequest, TaskResult
from ai_web_provider.core.provider.session import ProviderSession
from ai_web_provider.runtime.container import ProviderRuntimeContainer


class ProviderExecutor:
    def __init__(self, container: ProviderRuntimeContainer):
        self._container = container

    async def execute(self, request: TaskRequest) -> TaskResult:
        runtime = self._container.provider(request.provider)
        attempted: set[str] = set()
        last_error: Exception | None = None
        model = request.params.get("model") if isinstance(request.params.get("model"), str) else None
        for _ in range(self._container.settings.max_retries):
            slot = await runtime.pool.try_acquire(exclude=frozenset(attempted), model=model)
            if slot is None:
                break
            attempted.add(slot.email)
            try:
                account = runtime.accounts.get(slot.email)
                async with runtime.backend.browser_context(account, headless=self._container.settings.headless) as context:
                    page = await context.new_page()
                    try:
                        session = ProviderSession(account, page, self._container.paths, self._container.paths.outputs_dir, runtime.settings)
                        result = await runtime.adapter.execute(session, request)
                    finally:
                        await page.close()
                await runtime.accounts.record_success_async(account.email)
                return result
            except Exception as error:
                last_error = error
                policy = runtime.adapter.classify_failure(error) or default_classify_failure(error)
                await runtime.accounts.record_failure_async(slot.email)
                if policy.account_effect is AccountEffect.NEEDS_LOGIN:
                    await runtime.accounts.set_status_async(slot.email, AccountStatus.NEEDS_LOGIN)
                elif policy.account_effect is AccountEffect.COOLDOWN:
                    await runtime.accounts.set_cooldown_async(slot.email, timedelta(minutes=self._container.settings.cooldown_minutes))
                elif policy.account_effect is AccountEffect.QUOTA_COOLDOWN:
                    await runtime.accounts.set_cooldown_async(slot.email, timedelta(minutes=self._container.settings.quota_cooldown_minutes))
                elif policy.account_effect is AccountEffect.MODEL_QUOTA_COOLDOWN and policy.model:
                    await runtime.accounts.set_model_cooldown_async(slot.email, policy.model)
                if not policy.retryable:
                    raise
            finally:
                slot.release()
        if last_error is not None:
            raise last_error
        raise NoAvailableAccountError(f"no available account for provider `{request.provider}`")
