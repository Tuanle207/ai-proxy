"""aiosqlite-backed database: a single shared connection with helpers and transactions.

The service owns exactly one `Database` instance for its lifetime. All writes flow through the
repository layer over this single connection; WAL + a short `busy_timeout` absorb the
reader/writer overlap (§6.4). Never issue writes from `asyncio.to_thread` workers directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from aiosqlite import Row


class Database:
    """A thin wrapper over one shared `aiosqlite` connection."""

    def __init__(self, path: Path):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("database is not connected")
        return self._conn

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None = autocommit, so explicit BEGIN/COMMIT transactions work and
        # single-statement writes commit immediately (§6.4).
        conn = await aiosqlite.connect(self._path, isolation_level=None)
        conn.row_factory = Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA synchronous=NORMAL")
        self._conn = conn

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Cursor:
        return await self.conn.execute(sql, params)

    async def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[Row]:
        cursor = await self.conn.execute(sql, params)
        return list(await cursor.fetchall())

    async def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Row | None:
        cursor = await self.conn.execute(sql, params)
        return await cursor.fetchone()

    async def fetch_val(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        return row[0] if row is not None else None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        await self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            await self.conn.commit()
        except BaseException:
            await self.conn.rollback()
            raise

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def parse_iso_required(value: str) -> datetime:
    return datetime.fromisoformat(value)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None
