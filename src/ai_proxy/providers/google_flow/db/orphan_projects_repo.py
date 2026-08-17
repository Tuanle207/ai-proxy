"""Repository for `orphan_projects` — durable tracking of Flow projects a crash-recovered

job can no longer reference via `jobs.project_id` (that column gets overwritten by the next
retry attempt's new project; see `worker/recovery.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

from aiosqlite import Row

from ai_proxy.core.db.engine import Database, iso, utc_now


@dataclass
class OrphanProjectRecord:
    id: int
    account_email: str
    project_id: str
    reason: str


def _row_to_record(row: Row) -> OrphanProjectRecord:
    return OrphanProjectRecord(
        id=row["id"], account_email=row["account_email"],
        project_id=row["project_id"], reason=row["reason"],
    )


class OrphanProjectsRepo:
    def __init__(self, db: Database):
        self._db = db

    async def record(self, account_email: str, project_id: str, *, reason: str) -> None:
        await self._db.execute(
            "INSERT INTO gf_orphan_projects (account_email, project_id, reason, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (account_email, project_id, reason, iso(utc_now())),
        )

    async def list_pending(self) -> list[OrphanProjectRecord]:
        rows = await self._db.fetch_all(
            "SELECT id, account_email, project_id, reason FROM gf_orphan_projects "
            "WHERE cleaned_at IS NULL"
        )
        return [_row_to_record(r) for r in rows]

    async def mark_cleaned(self, record_id: int) -> None:
        await self._db.execute(
            "UPDATE gf_orphan_projects SET cleaned_at = ? WHERE id = ?",
            (iso(utc_now()), record_id),
        )
