"""POST /v1/upload — accept base64-encoded files and persist them to disk."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key

router = APIRouter(prefix="/v1", tags=["upload"], dependencies=[Depends(require_api_key)])

_DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+)(?:;base64)?,(?P<data>.+)$", re.DOTALL)


class UploadRequest(BaseModel):
    file_base64: str
    filename: str | None = None


class UploadResponse(BaseModel):
    media_id: str
    url: str


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.post("/upload", response_model=UploadResponse)
async def upload_file(request: Request, body: UploadRequest) -> UploadResponse:
    container = _container(request)
    match = _DATA_URI_RE.match(body.file_base64)
    if not match:
        raise HTTPException(422, "file_base64 must be a data URI (data:...;base64,...)")
    raw = base64.b64decode(match.group("data"))

    ext = "bin"
    if body.filename and "." in body.filename:
        ext = body.filename.rsplit(".", 1)[-1]
    storage_filename = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}.{ext}"
    rel_path = f"uploads/{storage_filename}"

    path = container.paths.outputs_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, raw)

    media_id = hashlib.sha256(raw).hexdigest()[:16]
    return UploadResponse(media_id=media_id, url=f"/download/{storage_filename}")
