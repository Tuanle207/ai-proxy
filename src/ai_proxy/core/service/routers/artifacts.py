"""Artifact library endpoints: list, metadata, file serving, thumbnails (§2.8, Phase 7).

Text artifacts are served inline; image/video/file artifacts stream from disk; thumbnails 404 for
non-visual kinds.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from email.utils import formatdate
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from PIL import Image

from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.service.schemas import ArtifactResponse, Page
from ai_proxy.core.service.serializers import artifact_to_response
from ai_proxy.core.worker.metadata import content_type_for

router = APIRouter(prefix="/v1", tags=["artifacts"], dependencies=[Depends(require_api_key)])

_VISUAL_KINDS = {"image", "video"}


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


def _resolve(container: ServiceContainer, rel_path: str) -> Path:
    try:
        return container.storage.resolve(rel_path)
    except ValueError as exc:
        raise HTTPException(404, "artifact not found") from exc


def _make_thumbnail(src: Path, dst: Path, size: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as image:
        image.thumbnail((size, size))
        image.save(dst, "PNG")


@router.get("/artifacts", response_model=Page[ArtifactResponse])
async def list_artifacts(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
    job_id: str | None = None,
    batch_id: str | None = None,
    kind: str | None = None,
    order: str = "created_at:desc",
) -> Page[ArtifactResponse]:
    container = _container(request)
    records, total = await container.artifacts.list_artifacts(
        page=page, page_size=page_size, from_dt=from_dt, to_dt=to_dt,
        job_id=job_id, batch_id=batch_id, kind=kind, order=order,
    )
    return Page(
        items=[artifact_to_response(record) for record in records],
        page=page, page_size=page_size, total=total,
        has_next=page * page_size < total,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(request: Request, artifact_id: str) -> ArtifactResponse:
    container = _container(request)
    artifact = await container.artifacts.get(artifact_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")
    return artifact_to_response(artifact)


@router.get("/artifacts/{artifact_id}/file", response_model=None)
async def get_artifact_file(
    request: Request, artifact_id: str
) -> FileResponse | Response:
    container = _container(request)
    artifact = await container.artifacts.get(artifact_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")

    if artifact.kind == "text":
        return PlainTextResponse(artifact.text_content or "", media_type="text/plain")

    if artifact.rel_path is None:
        raise HTTPException(404, "artifact file missing")
    path = _resolve(container, artifact.rel_path)
    if not path.is_file():
        raise HTTPException(404, "artifact file missing")

    headers = {"Cache-Control": "private, max-age=86400"}
    etag = f'"{artifact.sha256}"' if artifact.sha256 else None
    if etag:
        headers["ETag"] = etag
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and etag in {t.strip() for t in if_none_match.split(",")}:
            return Response(status_code=304, headers=headers)
    headers["Last-Modified"] = formatdate(path.stat().st_mtime, usegmt=True)
    media_type = artifact.mime or content_type_for(artifact.format)
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/artifacts/{artifact_id}/thumbnail", response_model=None)
async def get_thumbnail(
    request: Request,
    artifact_id: str,
    w: Annotated[int, Query(ge=1)] = 256,
) -> FileResponse:
    container = _container(request)
    artifact = await container.artifacts.get(artifact_id)
    if artifact is None:
        raise HTTPException(404, "artifact not found")
    if artifact.kind not in _VISUAL_KINDS:
        raise HTTPException(404, "thumbnail unavailable for non-visual artifact")
    if artifact.rel_path is None:
        raise HTTPException(404, "artifact file missing")
    size = min(w, container.settings.thumbnail_max_px)
    thumb_rel = f"{artifact.id}_{size}.png"
    thumb_dir = container.paths.thumbnails_dir
    thumb_path = thumb_dir / thumb_rel
    if artifact.thumbnail_rel_path != thumb_rel or not thumb_path.is_file():
        src = _resolve(container, artifact.rel_path)
        await asyncio.to_thread(_make_thumbnail, src, thumb_path, size)
        await container.artifacts.set_thumbnail(artifact.id, thumb_rel)
    return FileResponse(
        thumb_path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )
