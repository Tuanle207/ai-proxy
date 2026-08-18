"""WorkerEngine: provider-agnostic dispatch loop, worker tasks, cancellation, shutdown (§4.4).

A single dispatch loop pops jobs in priority+FIFO order, resolves the provider's runtime, acquires
a capacity-aware account slot (blocking only when every account of that provider is saturated),
marks the job running, and spawns a worker task. Retries are persisted to SQLite so they survive
restarts. A saturated provider cannot starve another (§6.2). All job lifecycle events are
published through the EventBus.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

import structlog

from ai_proxy.core.config import Settings
from ai_proxy.core.db.artifacts_repo import ArtifactsRepo
from ai_proxy.core.db.engine import utc_now
from ai_proxy.core.db.jobs_repo import JobRecord, JobsRepo
from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import AccountStatus, TaskResult
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.provider.runtime import ProviderRuntime
from ai_proxy.core.rotation.pool import AccountSlot
from ai_proxy.core.service.eta import EtaEstimator
from ai_proxy.core.service.schemas import (
    BatchCompletedEvent,
    BatchStatusEvent,
    JobCanceledEvent,
    JobCompletedEvent,
    JobFailedEvent,
    JobQueuedEvent,
    JobStatusEvent,
    QueueStatsEvent,
)
from ai_proxy.core.service.storage import StorageBackend
from ai_proxy.core.worker.bus import EventBus, publish_queue_stats_loop
from ai_proxy.core.worker.failure import AccountEffect, FailurePolicy, default_classify_failure
from ai_proxy.core.worker.runner import TaskRunner

TERMINAL_STATUSES = {"completed", "failed", "canceled"}
_STATS_INTERVAL_SECONDS = 5.0
_JOB_LOG_CONTEXT = ("job_id", "batch_id", "account_email")

_log = get_logger()


def derive_batch_status(statuses: list[str]) -> str:
    """Aggregate per-job statuses into a batch status (§4.6)."""
    if not statuses:
        return "queued"
    if any(status == "running" for status in statuses):
        return "running"
    if any(status == "queued" for status in statuses):
        return "running" if any(s in TERMINAL_STATUSES for s in statuses) else "queued"
    if all(status == "completed" for status in statuses):
        return "completed"
    if all(status == "failed" for status in statuses):
        return "failed"
    if all(status == "canceled" for status in statuses):
        return "canceled"
    return "partially_failed"


class JobQueue:
    """In-memory priority queue keyed by `(-priority, queued_at, job_id)` (§4.4)."""

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, float, str]] = asyncio.PriorityQueue()

    def enqueue(self, job_id: str, priority: int, queued_at: datetime) -> None:
        self._queue.put_nowait((-priority, queued_at.timestamp(), job_id))

    async def get(self) -> str:
        _, _, job_id = await self._queue.get()
        return job_id

    def task_done(self) -> None:
        self._queue.task_done()

    def qsize(self) -> int:
        return self._queue.qsize()


class WorkerEngine:
    def __init__(
        self,
        settings: Settings,
        paths: DataPaths,
        jobs: JobsRepo,
        artifacts: ArtifactsRepo,
        bus: EventBus,
        storage: StorageBackend,
        runner: TaskRunner,
        runtimes: dict[str, ProviderRuntime],
    ):
        self._settings = settings
        self._paths = paths
        self._jobs = jobs
        self._artifacts = artifacts
        self._bus = bus
        self._storage = storage
        self._runner = runner
        self._runtimes = runtimes
        self._queue = JobQueue()
        self._eta = EtaEstimator(
            sample_size=settings.eta_sample_size, default_seconds=settings.eta_default_seconds
        )
        self._dispatch_task: asyncio.Task[None] | None = None
        self._stats_task: asyncio.Task[None] | None = None
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_requests: set[str] = set()
        self._stop_event = asyncio.Event()
        self._completed_count = 0
        self._started_at = time.monotonic()

    @property
    def eta(self) -> EtaEstimator:
        return self._eta

    def total_slots(self) -> int:
        return sum(rt.pool.snapshot().total_slots for rt in self._runtimes.values())

    def _pool_totals(self) -> tuple[int, int]:
        total = free = 0
        for rt in self._runtimes.values():
            snapshot = rt.pool.snapshot()
            total += snapshot.total_slots
            free += snapshot.free_slots
        return total, free

    def _runtime_for(self, provider: str) -> ProviderRuntime:
        try:
            return self._runtimes[provider]
        except KeyError:
            raise ValueError(f"no runtime for provider {provider!r}") from None

    # --- lifecycle ---

    async def start(self) -> None:
        for job in await self._jobs.list_queued():
            self._queue.enqueue(job.id, job.priority, job.queued_at)
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        self._stats_task = asyncio.create_task(
            publish_queue_stats_loop(
                self._bus,
                self.stats_payload,
                interval=_STATS_INTERVAL_SECONDS,
                stop_event=self._stop_event,
            )
        )

    async def shutdown(self) -> None:
        self._stop_event.set()
        # Let the stats loop observe the stop event and finish any in-flight publish; cancelling
        # it mid-write races with aiosqlite's worker thread and logs "closed database".
        if self._stats_task is not None:
            try:
                await asyncio.wait_for(self._stats_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                self._stats_task.cancel()
                await asyncio.gather(self._stats_task, return_exceptions=True)
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            await asyncio.gather(self._dispatch_task, return_exceptions=True)
        tasks = list(self._running_tasks.values())
        if tasks:
            _, pending = await asyncio.wait(
                tasks, timeout=self._settings.shutdown_grace_seconds
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    # --- submission (used by the API) ---

    async def submit_jobs(self, jobs: list[JobRecord]) -> dict[str, int]:
        """Enqueue already-persisted jobs and emit `job.queued`; returns job_id -> position."""
        positions: dict[str, int] = {}
        base = self._queue.qsize()
        for index, job in enumerate(jobs):
            self._queue.enqueue(job.id, job.priority, job.queued_at)
            positions[job.id] = base + index
            await self._emit_queued(job, positions[job.id])
        return positions

    def queued_count(self) -> int:
        return self._queue.qsize()

    # --- dispatch ---

    async def _dispatch_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._dispatch_one(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Must never escape: an unhandled exception here would silently kill the whole
                # dispatch loop, leaving every future job stuck `queued` forever with no error.
                _log.exception("dispatch_loop_iteration_failed", job_id=job_id)
            finally:
                self._queue.task_done()

    async def _dispatch_one(self, job_id: str) -> None:
        job = await self._jobs.get_job(job_id)
        if job is None or job.status != "queued":
            return
        runtime = self._runtime_for(job.provider)
        slot = await runtime.pool.acquire(exclude=frozenset(job.attempted_emails))
        try:
            job = await self._jobs.get_job(job_id)
            if job is None or job.status != "queued":
                slot.release()
                return
            await self._jobs.mark_running(job_id, account_email=slot.email)
            await self._emit_status(job, "running", account_email=slot.email)
            _log.info(
                "job_started",
                job_id=job_id,
                account_email=slot.email,
                attempt=job.attempt,
                workspace_ref=job.workspace_ref,
            )
            task = asyncio.create_task(self._run_job(job, slot, runtime))
            self._running_tasks[job_id] = task
        except Exception:
            # The slot is only handed off to `_run_job` (which releases it) once the task is
            # created; any earlier failure here must release it itself or it leaks forever.
            slot.release()
            raise

    async def _run_job(
        self, job: JobRecord, slot: AccountSlot, runtime: ProviderRuntime
    ) -> None:
        email = slot.email
        structlog.contextvars.bind_contextvars(
            job_id=job.id, batch_id=job.batch_id, account_email=email
        )
        account = runtime.accounts.get(email)
        start = time.monotonic()
        try:
            try:
                if runtime.spec.capabilities.requires_browser:
                    async with runtime.backend.browser_context(account, headless=True) as context:
                        page = await context.new_page()
                        try:
                            result = await self._runner.run(job, account, page, runtime)
                        finally:
                            await page.close()
                else:
                    result = await self._runner.run(job, account, None, runtime)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if job.id in self._cancel_requests:
                    self._cancel_requests.discard(job.id)
                    return
                policy = runtime.adapter.classify_failure(exc) or default_classify_failure(exc)
                await self._handle_failure(
                    job, email, exc, time.monotonic() - start, runtime, policy
                )
                return
        finally:
            slot.release()
            self._running_tasks.pop(job.id, None)
            structlog.contextvars.unbind_contextvars(*_JOB_LOG_CONTEXT)

        duration = time.monotonic() - start
        if job.id in self._cancel_requests:
            self._cancel_requests.discard(job.id)
            return  # cancel_job already flipped the status; drop the success
        await self._finalize_success(job, result, duration, email, runtime)

    async def _finalize_success(
        self,
        job: JobRecord,
        result: TaskResult,
        duration: float,
        email: str,
        runtime: ProviderRuntime,
    ) -> None:
        artifact_count = len(result.artifacts)
        await self._jobs.complete(job.id, duration_seconds=duration)
        await runtime.accounts.record_success_async(email)
        self._eta.record(duration)
        self._completed_count += 1
        payload = JobCompletedEvent(
            job_id=job.id,
            batch_id=job.batch_id,
            image_count=artifact_count,
            duration_seconds=round(duration, 2),
            at=utc_now(),
        ).model_dump(mode="json")
        await self._bus.publish(
            type="job.completed", job_id=job.id, batch_id=job.batch_id,
            status="completed", payload=payload,
        )
        _log.info("job_completed", job_id=job.id, artifact_count=artifact_count)
        await self._update_batch_status(job.batch_id)

    async def _handle_failure(
        self,
        job: JobRecord,
        email: str,
        exc: Exception,
        duration: float,
        runtime: ProviderRuntime,
        policy: FailurePolicy,
    ) -> None:
        await runtime.accounts.record_failure_async(email)
        await self._apply_account_effect(runtime, email, policy)
        error_code = policy.error_code
        error_message = (str(exc) or type(exc).__name__)[:2000]
        attempted = list(job.attempted_emails)
        if email not in attempted:
            attempted.append(email)
        new_attempt = job.attempt + 1

        if policy.retryable and new_attempt < job.max_attempts:
            await self._jobs.requeue(
                job.id,
                attempt=new_attempt,
                attempted_emails=attempted,
                error_code=error_code,
                error_message=error_message,
            )
            self._queue.enqueue(job.id, job.priority, job.queued_at)
            payload = JobStatusEvent(
                job_id=job.id, batch_id=job.batch_id, status="queued",
                attempt=new_attempt, at=utc_now(),
            ).model_dump(mode="json")
            await self._bus.publish(
                type="job.status", job_id=job.id, batch_id=job.batch_id,
                status="queued", payload=payload,
            )
            _log.info(
                "job_requeued",
                job_id=job.id,
                attempt=new_attempt,
                error=error_code,
                workspace_ref=job.workspace_ref,
                attempted_emails=attempted,
            )
        else:
            await self._jobs.fail(
                job.id,
                attempt=new_attempt,
                attempted_emails=attempted,
                error_code=error_code,
                error_message=error_message,
                duration_seconds=duration,
            )
            payload = JobFailedEvent(
                job_id=job.id, batch_id=job.batch_id, error_code=error_code,
                error_message=error_message, attempt=new_attempt, at=utc_now(),
            ).model_dump(mode="json")
            await self._bus.publish(
                type="job.failed", job_id=job.id, batch_id=job.batch_id,
                status="failed", payload=payload,
            )
            _log.error("job_failed", job_id=job.id, error=error_code)
            await self._update_batch_status(job.batch_id)

    async def _apply_account_effect(
        self, runtime: ProviderRuntime, email: str, policy: FailurePolicy
    ) -> None:
        if policy.account_effect == AccountEffect.NEEDS_LOGIN:
            await runtime.accounts.set_status_async(email, AccountStatus.NEEDS_LOGIN)
        elif policy.account_effect == AccountEffect.QUOTA_COOLDOWN:
            await runtime.accounts.set_cooldown_async(
                email, timedelta(minutes=self._settings.quota_cooldown_minutes)
            )
        elif policy.account_effect == AccountEffect.COOLDOWN:
            await runtime.accounts.set_cooldown_async(
                email, timedelta(minutes=self._settings.cooldown_minutes)
            )

    # --- cancellation ---

    async def cancel_job(self, job_id: str) -> bool:
        job = await self._jobs.get_job(job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return False
        if job.status == "queued":
            await self._jobs.mark_canceled(job_id)
            await self._emit_canceled(job)
            await self._update_batch_status(job.batch_id)
            return True
        self._cancel_requests.add(job_id)
        await self._jobs.mark_canceled(job_id)
        await self._emit_canceled(job)
        await self._update_batch_status(job.batch_id)
        task = self._running_tasks.get(job_id)
        if task is not None:
            task.cancel()
        return True

    async def cancel_batch(self, batch_id: str) -> int:
        count = 0
        for job in await self._jobs.list_jobs_in_batch(batch_id):
            if await self.cancel_job(job.id):
                count += 1
        return count

    # --- events ---

    async def _emit_queued(self, job: JobRecord, position: int) -> None:
        payload = JobQueuedEvent(
            job_id=job.id, batch_id=job.batch_id, queue_position=position, at=utc_now()
        ).model_dump(mode="json")
        await self._bus.publish(
            type="job.queued", job_id=job.id, batch_id=job.batch_id,
            status="queued", payload=payload,
        )

    async def _emit_status(
        self, job: JobRecord, status: str, *, account_email: str | None = None
    ) -> None:
        payload = JobStatusEvent(
            job_id=job.id, batch_id=job.batch_id, status=status,
            account_email=account_email, attempt=job.attempt, at=utc_now(),
        ).model_dump(mode="json")
        await self._bus.publish(
            type="job.status", job_id=job.id, batch_id=job.batch_id,
            status=status, payload=payload,
        )

    async def _emit_canceled(self, job: JobRecord) -> None:
        payload = JobCanceledEvent(
            job_id=job.id, batch_id=job.batch_id, at=utc_now()
        ).model_dump(mode="json")
        await self._bus.publish(
            type="job.canceled", job_id=job.id, batch_id=job.batch_id,
            status="canceled", payload=payload,
        )

    async def _update_batch_status(self, batch_id: str) -> None:
        jobs = await self._jobs.list_jobs_in_batch(batch_id)
        new_status = derive_batch_status([job.status for job in jobs])
        await self._jobs.update_batch_status(batch_id, new_status)
        payload = BatchStatusEvent(
            batch_id=batch_id, status=new_status, at=utc_now()
        ).model_dump(mode="json")
        await self._bus.publish(
            type="batch.status", batch_id=batch_id, status=new_status, payload=payload
        )
        if new_status in TERMINAL_STATUSES or new_status == "partially_failed":
            completed = BatchCompletedEvent(
                batch_id=batch_id, status=new_status, at=utc_now()
            ).model_dump(mode="json")
            await self._bus.publish(
                type="batch.completed", batch_id=batch_id, status=new_status,
                payload=completed,
            )

    async def stats_payload(self) -> dict[str, Any]:
        counts = await self._jobs.count_by_status()
        total_slots, free_slots = self._pool_totals()
        queued = counts.get("queued", 0)
        running = counts.get("running", 0)
        avg: float | None = None
        eta: float | None = None
        if self._eta.is_ready() and total_slots > 0:
            avg = self._eta.avg_duration()
            eta = self._eta.finish_eta(max(queued - 1, 0), total_slots)
        elapsed_hours = max(time.monotonic() - self._started_at, 0.001) / 3600.0
        return QueueStatsEvent(
            queued=queued,
            running=running,
            free_slots=free_slots,
            total_slots=total_slots,
            throughput_jobs_per_hour=round(self._completed_count / elapsed_hours, 2),
            avg_duration_seconds=round(avg, 1) if avg is not None else None,
            eta_seconds=round(eta, 1) if eta is not None else None,
            at=utc_now(),
        ).model_dump(mode="json")
