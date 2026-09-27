"""Time helpers (extracted from db/engine.py to remove SQLite dependency)."""

from __future__ import annotations

from datetime import UTC, datetime


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
