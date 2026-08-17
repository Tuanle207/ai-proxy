"""Phase 6 tests: multi-provider dispatch, independent pools, recovery (no real browser)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ai_proxy.core.accounts.manager import AccountManager
from ai_proxy.core.config import Settings
from ai_proxy.core.db.engine import utc_now
from ai_proxy.core.db.jobs_repo import JobRecord
from ai_proxy.core.ids import new_id
from ai_proxy.core.models import AccountStatus, TaskRequest, TaskResult
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.provider import registry
from ai_proxy.core.provider.session import ProviderSession
from ai_proxy.core.rotation.pool import AccountSlotPool
from ai_proxy.core.rotation.strategy import RoundRobinStrategy
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.worker.failure import AccountEffect, FailurePolicy
from ai_proxy.core.worker.recovery import recover_orphaned_running
from tests.fakes import make_spec


def _job(provider: str, batch_id: str, prompt: str = "hello") -> JobRecord:
    now = utc_now()
    return JobRecord(
        id=new_id("job"),
        batch_id=batch_id,
        prompt=prompt,
        provider=provider,
        kind="text",
        params={},
        provider_state=None,
        count=1,
        timeout_seconds=30.0,
        priority=0,
        status="queued",
        attempt=0,
        max_attempts=2,
        attempted_emails=[],
        account_email=None,
        workspace_ref=None,
        error_code=None,
        error_message=None,
        queued_at=now,
        started_at=None,
        finished_at=None,
        duration_seconds=None,
        created_at=now,
        updated_at=now,
    )


def _activate(runtime: Any, email: str) -> None:
    runtime.accounts.add(email)
    runtime.accounts.set_status(email, AccountStatus.ACTIVE)


async def _wait_terminal(container: ServiceContainer, job_id: str) -> JobRecord:
    while True:
        job = await container.jobs.get_job(job_id)
        assert job is not None
        if job.status in ("completed", "failed", "canceled"):
            return job
        await asyncio.sleep(0.02)


def test_two_fake_providers_dispatch_independently(tmp_path: Path) -> None:
    async def main() -> None:
        registry.register(make_spec(name="alpha"))
        registry.register(make_spec(name="beta"))
        container = ServiceContainer(Settings(data_dir=str(tmp_path)))
        _activate(container.provider("alpha"), "a@example.com")
        _activate(container.provider("beta"), "b@example.com")

        batch_a = new_id("btc")
        batch_b = new_id("btc")
        job_a = _job("alpha", batch_a, "apple")
        job_b = _job("beta", batch_b, "banana")
        await container.startup()
        try:
            await container.jobs.create_batch_with_jobs(
                batch_a, idempotency_key=None, metadata=None, jobs=[job_a]
            )
            await container.jobs.create_batch_with_jobs(
                batch_b, idempotency_key=None, metadata=None, jobs=[job_b]
            )
            await container.engine.submit_jobs([job_a, job_b])
            done_a, done_b = await asyncio.gather(
                _wait_terminal(container, job_a.id),
                _wait_terminal(container, job_b.id),
            )
            assert done_a.status == "completed" and done_b.status == "completed"
            arts_a = await container.artifacts.list_by_job(job_a.id)
            arts_b = await container.artifacts.list_by_job(job_b.id)
        finally:
            await container.shutdown()

        assert [a.kind for a in arts_a] == ["text"]
        assert [a.kind for a in arts_b] == ["text"]
        assert arts_a[0].text_content == "fake:text:apple"
        assert arts_b[0].text_content == "fake:text:banana"

    asyncio.run(main())


def test_pools_share_machine_wide_cap_but_not_each_other(tmp_path: Path) -> None:
    async def main() -> None:
        paths = DataPaths(tmp_path)
        shared = asyncio.Semaphore(2)
        acc_a = AccountManager(paths, "alpha")
        acc_b = AccountManager(paths, "beta")
        acc_a.add("a@example.com")
        acc_b.add("b@example.com")
        acc_a.set_status("a@example.com", AccountStatus.ACTIVE)
        acc_b.set_status("b@example.com", AccountStatus.ACTIVE)
        pool_a = AccountSlotPool(
            acc_a, RoundRobinStrategy(), per_account_limit=1,
            max_concurrent_browsers=1, global_semaphore=shared,
        )
        pool_b = AccountSlotPool(
            acc_b, RoundRobinStrategy(), per_account_limit=1,
            max_concurrent_browsers=1, global_semaphore=shared,
        )

        slot_a = await pool_a.acquire()  # A is now at its own capacity
        slot_b = await pool_b.acquire()  # B is NOT blocked by A's saturation
        assert slot_a.email == "a@example.com" and slot_b.email == "b@example.com"
        slot_a.release()
        slot_b.release()

    asyncio.run(main())


def test_failing_provider_classified_independently(tmp_path: Path) -> None:
    async def main() -> None:
        registry.register(make_spec(name="ok"))
        registry.register(make_spec(name="boom"))
        container = ServiceContainer(Settings(data_dir=str(tmp_path)))
        _activate(container.provider("ok"), "ok@example.com")
        _activate(container.provider("boom"), "boom@example.com")

        class BoomAdapter:
            async def execute(self, session: ProviderSession, request: TaskRequest) -> TaskResult:
                raise ValueError("boom")

            def classify_failure(self, exc: BaseException) -> FailurePolicy | None:
                return FailurePolicy(False, "boom_error", AccountEffect.NONE)

            async def health_check(self, session: ProviderSession) -> bool:
                return True

            async def cleanup(self, session: ProviderSession, ref: str | None) -> None:
                return None

        container.provider("boom").adapter = BoomAdapter()

        batch = new_id("btc")
        ok_job = _job("ok", batch, "fine")
        boom_job = _job("boom", batch, "bad")
        await container.startup()
        try:
            await container.jobs.create_batch_with_jobs(
                batch, idempotency_key=None, metadata=None, jobs=[ok_job, boom_job]
            )
            await container.engine.submit_jobs([ok_job, boom_job])
            done_ok, done_boom = await asyncio.gather(
                _wait_terminal(container, ok_job.id),
                _wait_terminal(container, boom_job.id),
            )
        finally:
            await container.shutdown()

        assert done_ok.status == "completed"
        assert done_boom.status == "failed"
        assert done_boom.error_code == "boom_error"
        ok_account = container.provider("ok").accounts.get("ok@example.com")
        assert ok_account.fail_count == 0

    asyncio.run(main())


def test_recovery_requeues_and_archives_via_hook(tmp_path: Path) -> None:
    async def main() -> None:
        container = ServiceContainer(Settings(data_dir=str(tmp_path)))
        await container.db.connect()
        from ai_proxy.core.db.migrations import run_core_migrations

        await run_core_migrations(container.db)
        archived: list[str] = []
        batch = new_id("btc")
        job = _job("google_flow", batch)
        await container.jobs.create_batch_with_jobs(
            batch, idempotency_key=None, metadata=None, jobs=[job]
        )
        await container.jobs.mark_running(job.id, account_email="x@example.com")
        await container.jobs.set_workspace_ref(job.id, "proj-1")

        async def on_orphan(j: JobRecord) -> None:
            archived.append(j.workspace_ref or "")

        await recover_orphaned_running(container.jobs, on_orphan=on_orphan)
        requeued = await container.jobs.get_job(job.id)
        assert requeued is not None and requeued.status == "queued"
        assert archived == ["proj-1"]
        await container.db.close()

    asyncio.run(main())
