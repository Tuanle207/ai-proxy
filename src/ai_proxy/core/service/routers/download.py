"""GET /download/{filename} — public file serving from data/outputs."""

from __future__ import annotations

from email.utils import formatdate
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from ai_proxy.core.config import Settings

router = APIRouter(tags=["download"])

settings = Settings()
OUTPUTS_DIR = settings.paths.outputs_dir


def _resolve(filename: str) -> Path:
    """Walk outputs dir recursively looking for a file matching `filename`."""
    if not OUTPUTS_DIR.is_dir():
        raise HTTPException(404, "file not found")
    for path in OUTPUTS_DIR.rglob(filename):
        if path.is_file():
            return path
    raise HTTPException(404, "file not found")


@router.get("/download/{filename}")
async def download_file(filename: str) -> Response:
    path = _resolve(filename)
    headers = {"Cache-Control": "private, max-age=86400"}
    headers["Last-Modified"] = formatdate(path.stat().st_mtime, usegmt=True)
    return FileResponse(path, headers=headers)
