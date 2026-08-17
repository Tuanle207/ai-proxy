"""StorageBackend seam (§6.10): local disk today, cloud blob storage later.

`rel_path` values are keys *relative* to the backend root, never absolute (S-15). `LocalStorage`
enforces path containment on `resolve` so a malicious or backfilled `rel_path` can never escape
`outputs_dir`. The images table's `storage` column records which backend owns each object.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    bytes: int
    content_type: str


class StorageBackend(Protocol):
    @property
    def name(self) -> str: ...

    async def save(self, data: bytes, key: str) -> StoredObject: ...

    def resolve(self, key: str) -> Path: ...

    def public_url(self, key: str) -> str | None: ...


class LocalStorage:
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()

    @property
    def name(self) -> str:
        return "local"

    async def save(self, data: bytes, key: str) -> StoredObject:
        path = self.resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return StoredObject(key=key, bytes=len(data), content_type="application/octet-stream")

    def resolve(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"storage key escapes root: {key!r}")
        return path

    def public_url(self, key: str) -> str | None:
        return None
