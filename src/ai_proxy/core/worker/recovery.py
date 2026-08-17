"""Startup recovery of orphaned `running` jobs (S-11), provider-agnostic."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ai_proxy.core.db.jobs_repo import JobRecord, JobsRepo


async def recover_orphaned_running(
    jobs: JobsRepo,
    on_orphan: Callable[[JobRecord], Awaitable[None]] | None = None,
) -> int:
    """Re-queue jobs left `running` by a previous process; fail those past `max_attempts`.

    A running job's `workspace_ref` would otherwise be silently discarded once the next attempt
    overwrites it with a new one — archive it via `on_orphan` (each provider supplies its own
    cleanup hook) so the provider's recovery loop can still find it.
    """
    recovered = 0
    for job in await jobs.list_running():
        if job.workspace_ref is not None and on_orphan is not None:
            await on_orphan(job)
        if job.attempt >= job.max_attempts:
            await jobs.fail(
                job.id,
                attempt=job.attempt,
                attempted_emails=job.attempted_emails,
                error_code="interrupted",
                error_message="interrupted by restart and out of attempts",
            )
        else:
            await jobs.requeue(
                job.id,
                attempt=job.attempt,
                attempted_emails=job.attempted_emails,
                error_code="interrupted",
                error_message="recovered after restart",
            )
            recovered += 1
    return recovered
