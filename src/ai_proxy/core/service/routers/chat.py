"""POST /v1/chat/completions — direct adapter call to perplexity."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ai_proxy.core.ids import new_id
from ai_proxy.core.models import TaskKind, TaskRequest
from ai_proxy.core.provider.session import ProviderSession
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.time_utils import utc_now

router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(require_api_key)])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    workspace_ref: str | None = None
    medias: list[str] | None = None


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
) -> ChatCompletionResponse:
    container = _container(request)

    if body.stream:
        raise HTTPException(400, "streaming is not supported; set stream=false")
    if not body.messages:
        raise HTTPException(422, "messages must not be empty")

    prompt = body.messages[-1].content
    runtime = container.provider("perplexity")
    now = utc_now()

    task = TaskRequest(
        provider="perplexity",
        kind=TaskKind.TEXT,
        prompt=prompt,
        count=1,
        timeout=container.settings.default_timeout_seconds,
        params={"model": body.model},
        workspace_ref=body.workspace_ref,
    )

    slot = await runtime.pool.acquire()
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
                    on_workspace_created=lambda ref: None,
                )
                result = await runtime.adapter.execute(session, task)
            finally:
                await page.close()
    finally:
        slot.release()

    text_content = ""
    for art in result.artifacts:
        if art.text:
            text_content = art.text
            break

    created_ts = int(now.timestamp()) if now else 0
    completion_tokens = max(len(text_content) // 4, 0)
    prompt_tokens = max(len(prompt) // 4, 0)

    return ChatCompletionResponse(
        id=f"chatcmpl-{new_id('chat')}",
        created=created_ts,
        model=body.model,
        choices=[
            ChatChoice(
                message=ChatMessage(role="assistant", content=text_content),
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )
