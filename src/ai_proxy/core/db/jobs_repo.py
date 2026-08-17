"""Repository for batches and jobs (S-01, S-05, S-06).

Every write goes through this layer over the single shared connection. Rows are mapped to
dataclasses so the rest of the service never touches raw SQLite rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiosqlite import Row

from ai_proxy.core.db.engine import Database, iso, parse_iso, parse_iso_required, utc_now


@dataclass
class BatchRecord:
    id: str
    status: str
    job_count: int
    idempotency_key: str | None
    metadata: dict[str, Any] | None
    provider: str
    created_at: datetime
    updated_at: datetime


@dataclass
class JobRecord:
    id: str
    batch_id: str
    prompt: str
    provider: str
    kind: str
    params: dict[str, Any]
    provider_state: dict[str, Any] | None
    count: int
    timeout_seconds: float
    priority: int
    status: str
    attempt: int
    max_attempts: int
    attempted_emails: list[str]
    account_email: str | None
    workspace_ref: str | None
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None
    created_at: datetime
    updated_at: datetime


def _row_to_batch(row: Row) -> BatchRecord:
    metadata = row["metadata"]
    return BatchRecord(
        id=row["id"],
        status=row["status"],
        job_count=row["job_count"],
        idempotency_key=row["idempotency_key"],
        metadata=json.loads(metadata) if metadata else None,
        provider=row["provider"],
        created_at=parse_iso_required(row["created_at"]),
        updated_at=parse_iso_required(row["updated_at"]),
    )


def _row_to_job(row: Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        batch_id=row["batch_id"],
        prompt=row["prompt"],
        provider=row["provider"],
        kind=row["kind"],
        params=json.loads(row["params"] or "{}"),
        provider_state=json.loads(row["provider_state"]) if row["provider_state"] else None,
        count=row["count"],
        timeout_seconds=row["timeout_seconds"],
        priority=row["priority"],
        status=row["status"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
        attempted_emails=json.loads(row["attempted_emails"] or "[]"),
        account_email=row["account_email"],
        workspace_ref=row["workspace_ref"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        queued_at=parse_iso_required(row["queued_at"]),
        started_at=parse_iso(row["started_at"]),
        finished_at=parse_iso(row["finished_at"]),
        duration_seconds=row["duration_seconds"],
        created_at=parse_iso_required(row["created_at"]),
        updated_at=parse_iso_required(row["updated_at"]),
    )


_BATCH_COLUMNS = (
    "id, status, job_count, idempotency_key, metadata, provider, created_at, updated_at"
)
_JOB_COLUMNS = (
    "id, batch_id, prompt, provider, kind, params, provider_state, count, timeout_seconds, "
    "priority, status, attempt, max_attempts, attempted_emails, account_email, workspace_ref, "
    "error_code, error_message, queued_at, started_at, finished_at, duration_seconds, "
    "created_at, updated_at"
)
_JOB_VALUE_PLACEHOLDERS = ", ".join("?" for _ in _JOB_COLUMNS.split(","))


class JobsRepo:
    def __init__(self, db: Database):
        self._db = db

    # --- batches ---

    async def create_batch_with_jobs(
        self,
        batch_id: str,
        *,
        idempotency_key: str | None,
        metadata: dict[str, Any] | None,
        jobs: list[JobRecord],
    ) -> None:
        now = utc_now()
        provider = jobs[0].provider
        async with self._db.transaction():
            await self._db.execute(
                "INSERT INTO batches (id, status, job_count, idempotency_key, metadata, "
                "provider, created_at, updated_at) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)",
                (batch_id, len(jobs), idempotency_key,
                 json.dumps(metadata) if metadata else None, provider, iso(now), iso(now)),
            )
            for job in jobs:
                await self._insert_job(job)

    async def get_batch(self, batch_id: str) -> BatchRecord | None:
        row = await self._db.fetch_one(
            f"SELECT {_BATCH_COLUMNS} FROM batches WHERE id = ?", (batch_id,)
        )
        return _row_to_batch(row) if row else None

    async def get_batch_by_idempotency_key(self, key: str) -> BatchRecord | None:
        row = await self._db.fetch_one(
            f"SELECT {_BATCH_COLUMNS} FROM batches WHERE idempotency_key = ?", (key,)
        )
        return _row_to_batch(row) if row else None

    async def update_batch_status(self, batch_id: str, status: str) -> None:
        await self._db.execute(
            "UPDATE batches SET status = ?, updated_at = ? WHERE id = ?",
            (status, iso(utc_now()), batch_id),
        )

    # --- jobs ---

    async def _insert_job(self, job: JobRecord) -> None:
        await self._db.execute(
            f"INSERT INTO jobs ({_JOB_COLUMNS}) VALUES ({_JOB_VALUE_PLACEHOLDERS})",
            (
                job.id, job.batch_id, job.prompt, job.provider, job.kind,
                json.dumps(job.params),
                json.dumps(job.provider_state) if job.provider_state else None,
                job.count, job.timeout_seconds, job.priority, job.status,
                job.attempt, job.max_attempts, json.dumps(job.attempted_emails),
                job.account_email, job.workspace_ref, job.error_code, job.error_message,
                iso(job.queued_at), iso(job.started_at), iso(job.finished_at),
                job.duration_seconds, iso(job.created_at), iso(job.updated_at),
            ),
        )

    async def get_job(self, job_id: str) -> JobRecord | None:
        row = await self._db.fetch_one(
            f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = ?", (job_id,)
        )
        return _row_to_job(row) if row else None

    async def list_jobs(
        self,
        *,
        statuses: list[str] | None = None,
        batch_id: str | None = None,
        provider: str | None = None,
        page: int = 1,
        page_size: int = 50,
        order: str = "queued_at:desc",
    ) -> tuple[list[JobRecord], int]:
        where: list[str] = []
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if batch_id is not None:
            where.append("batch_id = ?")
            params.append(batch_id)
        if provider is not None:
            where.append("provider = ?")
            params.append(provider)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        total = int(
            await self._db.fetch_val(
                f"SELECT COUNT(*) FROM jobs {where_sql}", tuple(params)
            )
            or 0
        )

        column, _, direction = order.partition(":")
        if column not in {"queued_at", "created_at", "updated_at", "priority"}:
            column = "queued_at"
        direction = "ASC" if direction.upper() == "ASC" else "DESC"
        offset = max(page - 1, 0) * page_size
        rows = await self._db.fetch_all(
            f"SELECT {_JOB_COLUMNS} FROM jobs {where_sql} "
            f"ORDER BY {column} {direction}, id LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )
        return [_row_to_job(r) for r in rows], total

    async def list_jobs_in_batch(self, batch_id: str) -> list[JobRecord]:
        rows = await self._db.fetch_all(
            f"SELECT {_JOB_COLUMNS} FROM jobs WHERE batch_id = ? ORDER BY queued_at ASC",
            (batch_id,),
        )
        return [_row_to_job(r) for r in rows]

    async def list_queued(self, *, provider: str | None = None) -> list[JobRecord]:
        if provider is None:
            rows = await self._db.fetch_all(
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE status = 'queued' "
                "ORDER BY priority DESC, queued_at ASC, id ASC"
            )
        else:
            rows = await self._db.fetch_all(
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE status = 'queued' AND provider = ? "
                "ORDER BY priority DESC, queued_at ASC, id ASC",
                (provider,),
            )
        return [_row_to_job(r) for r in rows]

    async def list_running(self, *, provider: str | None = None) -> list[JobRecord]:
        if provider is None:
            rows = await self._db.fetch_all(
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE status = 'running'"
            )
        else:
            rows = await self._db.fetch_all(
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE status = 'running' AND provider = ?",
                (provider,),
            )
        return [_row_to_job(r) for r in rows]

    async def count_by_status(self, *, provider: str | None = None) -> dict[str, int]:
        if provider is None:
            rows = await self._db.fetch_all(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
            )
        else:
            rows = await self._db.fetch_all(
                "SELECT status, COUNT(*) AS n FROM jobs WHERE provider = ? GROUP BY status",
                (provider,),
            )
        return {row["status"]: int(row["n"]) for row in rows}

    async def mark_running(
        self, job_id: str, *, account_email: str, started_at: datetime | None = None
    ) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = 'running', account_email = ?, started_at = ?, "
            "error_code = NULL, error_message = NULL, finished_at = NULL, updated_at = ? "
            "WHERE id = ?",
            (account_email, iso(started_at or utc_now()), iso(utc_now()), job_id),
        )

    async def set_workspace_ref(self, job_id: str, workspace_ref: str) -> None:
        await self._db.execute(
            "UPDATE jobs SET workspace_ref = ?, updated_at = ? WHERE id = ?",
            (workspace_ref, iso(utc_now()), job_id),
        )

    async def clear_workspace_ref(self, job_id: str) -> None:
        await self._db.execute(
            "UPDATE jobs SET workspace_ref = NULL, updated_at = ? WHERE id = ?",
            (iso(utc_now()), job_id),
        )

    async def list_orphaned_projects(self) -> list[JobRecord]:
        rows = await self._db.fetch_all(
            f"SELECT {_JOB_COLUMNS} FROM jobs "
            "WHERE workspace_ref IS NOT NULL AND status IN ('completed','failed','canceled')"
        )
        return [_row_to_job(r) for r in rows]

    async def complete(
        self, job_id: str, *, finished_at: datetime | None = None, duration_seconds: float
    ) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = 'completed', finished_at = ?, duration_seconds = ?, "
            "error_code = NULL, error_message = NULL, updated_at = ? WHERE id = ?",
            (iso(finished_at or utc_now()), duration_seconds, iso(utc_now()), job_id),
        )

    async def requeue(
        self,
        job_id: str,
        *,
        attempt: int,
        attempted_emails: list[str],
        error_code: str,
        error_message: str,
    ) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = 'queued', attempt = ?, attempted_emails = ?, "
            "error_code = ?, error_message = ?, account_email = NULL, started_at = NULL, "
            "finished_at = NULL, duration_seconds = NULL, updated_at = ? WHERE id = ?",
            (attempt, json.dumps(attempted_emails), error_code, error_message,
             iso(utc_now()), job_id),
        )

    async def fail(
        self,
        job_id: str,
        *,
        attempt: int,
        attempted_emails: list[str],
        error_code: str,
        error_message: str,
        finished_at: datetime | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = 'failed', attempt = ?, attempted_emails = ?, "
            "error_code = ?, error_message = ?, finished_at = ?, duration_seconds = ?, "
            "updated_at = ? WHERE id = ?",
            (attempt, json.dumps(attempted_emails), error_code, error_message,
             iso(finished_at or utc_now()), duration_seconds, iso(utc_now()), job_id),
        )

    async def mark_canceled(self, job_id: str) -> None:
        await self._db.execute(
            "UPDATE jobs SET status = 'canceled', finished_at = ?, updated_at = ? WHERE id = ?",
            (iso(utc_now()), iso(utc_now()), job_id),
        )
