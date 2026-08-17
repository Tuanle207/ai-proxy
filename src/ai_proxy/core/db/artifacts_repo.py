"""Repository for artifact metadata (S-07, S-08, S-20).

Generalized beyond images to any kind of generated output (text / image / video / file).
`rel_path` is always relative to `outputs_dir` (never absolute — see S-15); the serving handler
joins it and asserts path containment before opening the file. Non-visual kinds have a null
`rel_path`/`bytes` and may store their content inline in `text_content`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiosqlite import Row

from ai_proxy.core.db.engine import Database, iso, parse_iso_required


@dataclass
class ArtifactRecord:
    id: str
    job_id: str | None
    storage: str
    rel_path: str | None
    source_url: str | None
    kind: str
    mime: str | None
    text_content: str | None
    meta: dict[str, Any]
    bytes: int | None
    width: int | None
    height: int | None
    format: str | None
    sha256: str | None
    prompt: str | None
    account_email: str | None
    thumbnail_rel_path: str | None
    created_at: datetime


_ARTIFACT_COLUMNS = (
    "id, job_id, storage, rel_path, source_url, kind, mime, text_content, meta, bytes, "
    "width, height, format, sha256, prompt, account_email, thumbnail_rel_path, created_at"
)
_ARTIFACT_VALUE_PLACEHOLDERS = ", ".join("?" for _ in _ARTIFACT_COLUMNS.split(","))


def _row_to_artifact(row: Row) -> ArtifactRecord:
    return ArtifactRecord(
        id=row["id"],
        job_id=row["job_id"],
        storage=row["storage"],
        rel_path=row["rel_path"],
        source_url=row["source_url"],
        kind=row["kind"],
        mime=row["mime"],
        text_content=row["text_content"],
        meta=json.loads(row["meta"]) if row["meta"] else {},
        bytes=row["bytes"],
        width=row["width"],
        height=row["height"],
        format=row["format"],
        sha256=row["sha256"],
        prompt=row["prompt"],
        account_email=row["account_email"],
        thumbnail_rel_path=row["thumbnail_rel_path"],
        created_at=parse_iso_required(row["created_at"]),
    )


class ArtifactsRepo:
    def __init__(self, db: Database):
        self._db = db

    async def insert(self, artifact: ArtifactRecord) -> None:
        await self._insert_one(artifact)

    async def insert_many(self, artifacts: list[ArtifactRecord]) -> None:
        async with self._db.transaction():
            for artifact in artifacts:
                await self._insert_one(artifact)

    async def _insert_one(self, artifact: ArtifactRecord) -> None:
        await self._db.execute(
            f"INSERT OR IGNORE INTO artifacts ({_ARTIFACT_COLUMNS}) "
            f"VALUES ({_ARTIFACT_VALUE_PLACEHOLDERS})",
            (
                artifact.id, artifact.job_id, artifact.storage, artifact.rel_path,
                artifact.source_url, artifact.kind, artifact.mime, artifact.text_content,
                json.dumps(artifact.meta), artifact.bytes, artifact.width, artifact.height,
                artifact.format, artifact.sha256, artifact.prompt, artifact.account_email,
                artifact.thumbnail_rel_path, iso(artifact.created_at),
            ),
        )

    async def get(self, artifact_id: str) -> ArtifactRecord | None:
        row = await self._db.fetch_one(
            f"SELECT {_ARTIFACT_COLUMNS} FROM artifacts WHERE id = ?", (artifact_id,)
        )
        return _row_to_artifact(row) if row else None

    async def exists_by_rel_path(self, rel_path: str) -> bool:
        value = await self._db.fetch_val(
            "SELECT 1 FROM artifacts WHERE rel_path = ? LIMIT 1", (rel_path,)
        )
        return value is not None

    async def list_by_job(self, job_id: str) -> list[ArtifactRecord]:
        rows = await self._db.fetch_all(
            f"SELECT {_ARTIFACT_COLUMNS} FROM artifacts WHERE job_id = ? "
            "ORDER BY created_at ASC",
            (job_id,),
        )
        return [_row_to_artifact(r) for r in rows]

    async def list_artifacts(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        job_id: str | None = None,
        batch_id: str | None = None,
        kind: str | None = None,
        order: str = "created_at:desc",
    ) -> tuple[list[ArtifactRecord], int]:
        where: list[str] = []
        params: list[Any] = []
        join = ""
        if from_dt is not None:
            where.append("artifacts.created_at >= ?")
            params.append(iso(from_dt))
        if to_dt is not None:
            where.append("artifacts.created_at <= ?")
            params.append(iso(to_dt))
        if job_id is not None:
            where.append("artifacts.job_id = ?")
            params.append(job_id)
        if batch_id is not None:
            join = " JOIN jobs j ON artifacts.job_id = j.id"
            where.append("j.batch_id = ?")
            params.append(batch_id)
        if kind is not None:
            where.append("artifacts.kind = ?")
            params.append(kind)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        total = int(
            await self._db.fetch_val(
                f"SELECT COUNT(*) FROM artifacts{join} {where_sql}", tuple(params)
            )
            or 0
        )

        column, _, direction = order.partition(":")
        if column not in {"created_at", "id", "bytes"}:
            column = "created_at"
        direction = "ASC" if direction.upper() == "ASC" else "DESC"
        offset = max(page - 1, 0) * page_size
        rows = await self._db.fetch_all(
            f"SELECT {_ARTIFACT_COLUMNS} FROM artifacts{join} {where_sql} "
            f"ORDER BY artifacts.{column} {direction}, artifacts.id LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )
        return [_row_to_artifact(r) for r in rows], total

    async def delete(self, artifact_id: str) -> None:
        await self._db.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))

    async def set_thumbnail(self, artifact_id: str, thumbnail_rel_path: str) -> None:
        await self._db.execute(
            "UPDATE artifacts SET thumbnail_rel_path = ? WHERE id = ?",
            (thumbnail_rel_path, artifact_id),
        )

    async def stats(self) -> tuple[int, int]:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS b FROM artifacts"
        )
        if row is None:
            return 0, 0
        return int(row["n"]), int(row["b"])
