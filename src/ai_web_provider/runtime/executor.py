"""Single owner of browser execution, retries, account effects and failure captures."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import timedelta
from typing import Any

import structlog

from ai_web_provider.core import diagnostics
from ai_web_provider.core.errors import NoAvailableAccountError, TaskFailedError
from ai_web_provider.core.failure import AccountEffect, FailurePolicy, default_classify_failure
from ai_web_provider.core.logging_setup import get_logger
from ai_web_provider.core.models import AccountStatus, AttemptRecord, TaskRequest, TaskResult
from ai_web_provider.core.provider.session import ProviderSession
from ai_web_provider.runtime.container import ProviderRuntimeContainer

_log = get_logger()
_PRUNE_INTERVAL_SECONDS = 3600.0


class ProviderExecutor:
    def __init__(self, container: ProviderRuntimeContainer):
        self._container = container
        self._last_prune: float | None = None

    async def execute(self, request: TaskRequest) -> TaskResult:
        if not request.request_id:
            request = request.model_copy(update={"request_id": f"req_{uuid.uuid4().hex[:12]}"})
        request_id = request.request_id
        assert request_id is not None
        with structlog.contextvars.bound_contextvars(
            request_id=request_id, provider=request.provider
        ):
            return await self._execute(request, request_id)

    async def _execute(self, request: TaskRequest, request_id: str) -> TaskResult:
        runtime = self._container.provider(request.provider)
        attempted: set[str] = set()
        attempts: list[AttemptRecord] = []
        last_error: Exception | None = None
        model_value = request.params.get("model")
        model = model_value if isinstance(model_value, str) else None
        for attempt in range(1, self._container.settings.max_retries + 1):
            slot = await runtime.pool.acquire(exclude=frozenset(attempted), model=model)
            attempted.add(slot.email)
            started = time.monotonic()
            diagnostics.start_attempt()
            capture: dict[str, str | None] = {}
            try:
                with structlog.contextvars.bound_contextvars(
                    attempt=attempt, account_email=slot.email
                ):
                    try:
                        result = await self._run_attempt(runtime, request, slot.email, capture)
                    except Exception as error:
                        last_error = error
                        record, policy = await self._handle_failure(
                            runtime, attempt, slot.email, error, started, capture.get("id")
                        )
                        attempts.append(record)
                        if not policy.retryable:
                            raise TaskFailedError(
                                request_id=request_id, attempts=attempts, last_error=error
                            ) from error
                        continue
                    attempts.append(
                        AttemptRecord(
                            attempt=attempt,
                            account_email=slot.email,
                            ok=True,
                            duration_seconds=round(time.monotonic() - started, 2),
                        )
                    )
                    _log.info(
                        "attempt_succeeded",
                        duration_seconds=round(time.monotonic() - started, 2),
                        step_timings=diagnostics.step_timings(),
                    )
                    await runtime.accounts.record_success_async(slot.email)
                    return result.model_copy(update={"attempts": attempts})
            finally:
                slot.release()
                structlog.contextvars.unbind_contextvars("step", "workspace_ref")
        if last_error is not None:
            raise TaskFailedError(
                request_id=request_id, attempts=attempts, last_error=last_error
            ) from last_error
        raise NoAvailableAccountError(f"no available account for provider `{request.provider}`")

    async def _run_attempt(
        self, runtime: Any, request: TaskRequest, email: str, capture: dict[str, str | None]
    ) -> TaskResult:
        account = runtime.accounts.get(email)
        async with runtime.backend.browser_context(account) as context:
            page = await context.new_page()
            browser_settings = self._container.settings.browser
            await page.set_viewport_size(
                {
                    "width": browser_settings.viewport_width,
                    "height": browser_settings.viewport_height,
                }
            )
            recorder = diagnostics.PageEventRecorder().attach(page)
            try:
                session = ProviderSession(
                    account,
                    page,
                    self._container.paths,
                    self._container.paths.outputs_dir,
                    runtime.settings,
                )
                result: TaskResult = await runtime.adapter.execute(session, request)
                return result
            except Exception as error:
                # Capture while the page still shows the failing state (before it is closed).
                capture["id"] = await self._capture(page, request, error, recorder)
                raise
            finally:
                await page.close()

    async def _capture(
        self,
        page: Any,
        request: TaskRequest,
        error: BaseException,
        recorder: diagnostics.PageEventRecorder,
    ) -> str | None:
        context = structlog.contextvars.get_contextvars()
        meta = {
            "request_id": context.get("request_id"),
            "attempt": context.get("attempt"),
            "provider": request.provider,
            "account_email": context.get("account_email"),
            "workspace_ref": context.get("workspace_ref") or request.workspace_ref,
            "step": context.get("step"),
            "kind": str(request.kind),
            "prompt_chars": len(request.prompt),
            "input_count": len(request.inputs),
            "count": request.count,
            "timeout": request.timeout,
            "params": request.params,
        }
        capture_id = await diagnostics.capture_failure(
            page,
            failures_dir=self._container.paths.failures_dir,
            error=error,
            meta=meta,
            recorder=recorder,
        )
        await self._maybe_prune()
        return capture_id

    async def _handle_failure(
        self,
        runtime: Any,
        attempt: int,
        email: str,
        error: Exception,
        started: float,
        capture_id: str | None,
    ) -> tuple[AttemptRecord, FailurePolicy]:
        policy = runtime.adapter.classify_failure(error) or default_classify_failure(error)
        record = AttemptRecord(
            attempt=attempt,
            account_email=email,
            ok=False,
            step=diagnostics.current_step(),
            error_code=policy.error_code,
            error_type=type(error).__name__,
            capture_id=capture_id,
            duration_seconds=round(time.monotonic() - started, 2),
        )
        _log.warning(
            "attempt_failed",
            error_code=policy.error_code,
            error_type=type(error).__name__,
            error_message=str(error)[:500],
            account_effect=str(policy.account_effect),
            retryable=policy.retryable,
            capture_id=capture_id,
            duration_seconds=record.duration_seconds,
            step_timings=diagnostics.step_timings(),
        )
        await runtime.accounts.record_failure_async(email)
        if policy.account_effect is AccountEffect.NEEDS_LOGIN:
            await runtime.accounts.set_status_async(email, AccountStatus.NEEDS_LOGIN)
        elif policy.account_effect is AccountEffect.COOLDOWN:
            await runtime.accounts.set_cooldown_async(
                email, timedelta(minutes=self._container.settings.cooldown_minutes)
            )
        elif policy.account_effect is AccountEffect.QUOTA_COOLDOWN:
            await runtime.accounts.set_cooldown_async(
                email, timedelta(minutes=self._container.settings.quota_cooldown_minutes)
            )
        elif policy.account_effect is AccountEffect.MODEL_QUOTA_COOLDOWN and policy.model:
            await runtime.accounts.set_model_cooldown_async(email, policy.model)
        return record, policy

    async def _maybe_prune(self) -> None:
        now = time.monotonic()
        if self._last_prune is not None and now - self._last_prune < _PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune = now
        settings = self._container.settings
        try:
            removed = await asyncio.to_thread(
                diagnostics.prune_failures,
                self._container.paths.failures_dir,
                max_age_days=settings.failure_retention_days,
                max_total_mb=settings.failure_retention_max_mb,
            )
            if removed:
                _log.info("failure_captures_pruned", removed=removed)
        except Exception:
            _log.warning("failure_captures_prune_failed", exc_info=True)
