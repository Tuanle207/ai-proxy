"""Startup indexing of pre-existing files under `data/outputs/` (S-20, §6.8).

Idempotent via `rel_path` uniqueness. The true format is sniffed with Pillow because Flow saves
JPEG bytes under a `.png` name; `created_at` is the file mtime.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ai_proxy.core.db.artifacts_repo import ArtifactRecord, ArtifactsRepo
from ai_proxy.core.ids import new_id
from ai_proxy.core.paths import DataPaths
from ai_proxy.core.service.storage import LocalStorage
from ai_proxy.core.worker.metadata import content_type_for, extract_image_metadata


async def backfill_images(artifacts: ArtifactsRepo, storage: LocalStorage, paths: DataPaths) -> int:
    outputs = paths.outputs_dir
    if not outputs.is_dir():
        return 0
    indexed = 0
    for path in outputs.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(outputs).as_posix()
        if await artifacts.exists_by_rel_path(rel_path):
            continue
        meta = await asyncio.to_thread(extract_image_metadata, path)
        created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        await artifacts.insert(
            ArtifactRecord(
                id=new_id("img"),
                job_id=None,
                storage=storage.name,
                rel_path=rel_path,
                source_url=None,
                kind="image",
                mime=content_type_for(meta.format),
                text_content=None,
                meta={},
                bytes=meta.bytes,
                width=meta.width,
                height=meta.height,
                format=meta.format,
                sha256=meta.sha256,
                prompt=None,
                account_email=None,
                thumbnail_rel_path=None,
                created_at=created_at,
            )
        )
        indexed += 1
    return indexed
