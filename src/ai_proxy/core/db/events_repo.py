"""Repository for the `job_events` table (S-04).

Events are persisted first and assigned a monotonic `seq` (the SSE event id), so a reconnecting
client can replay exactly from `Last-Event-ID` with no gaps or dupes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiosqlite import Row

from ai_proxy.core.db.engine import Database, iso, parse_iso_required, utc_now


@dataclass
class EventRecord:
    seq: int
    job_id: str | None
    batch_id: str | None
    type: str
    status: str | None
    payload: dict[str, Any]
    created_at: datetime


_EVENT_COLUMNS = "seq, job_id, batch_id, type, status, payload, created_at"


def _row_to_event(row: Row) -> EventRecord:
    return EventRecord(
        seq=row["seq"],
        job_id=row["job_id"],
        batch_id=row["batch_id"],
        type=row["type"],
        status=row["status"],
        payload=json.loads(row["payload"]),
        created_at=parse_iso_required(row["created_at"]),
    )


class EventsRepo:
    def __init__(self, db: Database):
        self._db = db

    async def append(
        self,
        *,
        job_id: str | None,
        batch_id: str | None,
        type: str,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now()
        cursor = await self._db.execute(
            "INSERT INTO job_events (job_id, batch_id, type, status, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, batch_id, type, status, json.dumps(payload or {}), iso(now)),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    async def replay(
        self,
        *,
        after_seq: int,
        job_id: str | None = None,
        batch_id: str | None = None,
        types: list[str] | None = None,
        limit: int = 500,
    ) -> list[EventRecord]:
        where = ["seq > ?"]
        params: list[Any] = [after_seq]
        if job_id is not None:
            where.append("job_id = ?")
            params.append(job_id)
        if batch_id is not None:
            where.append("batch_id = ?")
            params.append(batch_id)
        if types:
            where.append(f"type IN ({', '.join('?' for _ in types)})")
            params.extend(types)
        rows = await self._db.fetch_all(
            f"SELECT {_EVENT_COLUMNS} FROM job_events WHERE {' AND '.join(where)} "
            "ORDER BY seq ASC LIMIT ?",
            tuple(params) + (limit,),
        )
        return [_row_to_event(r) for r in rows]

    async def prune(self, older_than_seq: int) -> None:
        await self._db.execute("DELETE FROM job_events WHERE seq < ?", (older_than_seq,))
