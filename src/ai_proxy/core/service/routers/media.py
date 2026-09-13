"""GET /v1/media/{media_id}/urls — resolve a media_id to download URLs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_proxy.core.service.deps import require_api_key

router = APIRouter(prefix="/v1", tags=["media"], dependencies=[Depends(require_api_key)])


class MediaUrlEntry(BaseModel):
    provider: str
    name: str
    url: str


class MediaUrlsResponse(BaseModel):
    media_id: str
    urls: list[MediaUrlEntry]


@router.get("/media/{media_id}/urls", response_model=MediaUrlsResponse)
async def get_media_urls(media_id: str) -> MediaUrlsResponse:
    return MediaUrlsResponse(
        media_id=media_id,
        urls=[MediaUrlEntry(provider="local", name="", url=f"/download/{media_id}")],
    )
