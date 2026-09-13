"""POST /v1/images/generations — direct adapter call to google_flow."""

from __future__ import annotations

import base64
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AliasChoices, BaseModel, Field

from ai_proxy.core.logging_setup import get_logger
from ai_proxy.core.models import TaskKind, TaskRequest
from ai_proxy.core.provider.session import ProviderSession
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.time_utils import utc_now

router = APIRouter(prefix="/v1", tags=["images"], dependencies=[Depends(require_api_key)])

_log = get_logger()

_MAX_N = 4
_ASPECT_RATIO_MAP: dict[str, str] = {
    "1024x1024": "1:1",
    "768x1024": "3:4",
    "1024x768": "4:3",
    "768x1376": "9:16",
    "1376x768": "16:9",
    "768x1706": "9:18",
    "1706x768": "18:9",
}


def _size_to_aspect_ratio(size: str) -> str:
    ratio = _ASPECT_RATIO_MAP.get(size)
    if ratio is None:
        supported = ", ".join(_ASPECT_RATIO_MAP)
        raise HTTPException(422, f"unsupported size {size!r}; supported: {supported}")
    return ratio


class ImageGenerationRequest(BaseModel):
    model: str
    prompt: str
    n: int = Field(default=1, ge=1)
    size: str = "1024x1024"
    response_format: str = "url"
    medias: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("medias", "ref_media_ids"),
    )


class ImageObject(BaseModel):
    url: str | None = None
    b64_json: str | None = None


class ImageGenerationResponse(BaseModel):
    created: int
    data: list[ImageObject]


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.post("/images/generations", response_model=ImageGenerationResponse)
async def image_generations(
    request: Request,
    body: ImageGenerationRequest,
) -> ImageGenerationResponse:
    container = _container(request)

    if body.n > _MAX_N:
        raise HTTPException(422, f"n must be <= {_MAX_N}")

    aspect_ratio = _size_to_aspect_ratio(body.size)
    runtime = container.provider("google_flow")
    params = {
        "model": body.model,
        "aspect_ratio": aspect_ratio,
        "reuse_default_project": True,
    }

    now = utc_now()
    task = TaskRequest(
        provider="google_flow",
        kind=TaskKind.IMAGE,
        prompt=body.prompt,
        count=body.n,
        timeout=container.settings.default_timeout_seconds,
        params=params,
    )

    slot = await runtime.pool.acquire(model=body.model)
    try:
        account = runtime.accounts.get(slot.email)
        async with runtime.backend.browser_context(
            account, headless=container.settings.headless
        ) as context:
            page = await context.new_page()
            try:
                session = ProviderSession(
                    account=account,
                    page=page,
                    paths=container.paths,
                    output_dir=container.paths.outputs_dir,
                    settings=runtime.settings,
                )
                result = await runtime.adapter.execute(session, task)
            finally:
                await page.close()
    finally:
        slot.release()

    created_ts = int(now.timestamp()) if now else 0
    data: list[ImageObject] = []
    for art in result.artifacts:
        if art.kind != TaskKind.IMAGE or art.rel_path is None:
            continue
        filename = art.rel_path.name
        if body.response_format == "b64_json":
            path = container.paths.outputs_dir / art.rel_path
            b64 = base64.b64encode(path.read_bytes()).decode()
            data.append(ImageObject(b64_json=b64))
        else:
            data.append(ImageObject(url=f"/download/{filename}"))

    return ImageGenerationResponse(created=created_ts, data=data)
