"""SSE endpoint: GET /v1/events (§3.3, S-04).

Replay is exact: we subscribe first, then replay the backlog up to the current `seq`, then drain
the live queue skipping anything already replayed. That gives no gap and no dupes across a
reconnect using `Last-Event-ID`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request
from sse_starlette.sse import EventSourceResponse

from ai_proxy.core.db.events_repo import EventRecord
from ai_proxy.core.service.container import ServiceContainer
from ai_proxy.core.service.deps import require_api_key
from ai_proxy.core.worker.bus import Subscription

router = APIRouter(prefix="/v1", tags=["events"], dependencies=[Depends(require_api_key)])


def _container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


def _to_sse(event: EventRecord) -> dict[str, str]:
    return {
        "id": str(event.seq),
        "event": event.type,
        "data": json.dumps(event.payload),
    }


async def _event_generator(
    container: ServiceContainer,
    sub: Subscription,
    *,
    job_id: str | None,
    batch_id: str | None,
    types: list[str] | None,
    last_event_id: int,
) -> AsyncIterator[dict[str, str]]:
    last_yielded = last_event_id
    try:
        backlog = await container.events.replay(
            after_seq=last_event_id, job_id=job_id, batch_id=batch_id, types=types
        )
        for event in backlog:
            yield _to_sse(event)
            last_yielded = max(last_yielded, event.seq)
        while True:
            event = await sub.queue.get()
            if event.type == "stream.overflow":
                yield _to_sse(event)
                return
            if event.seq <= last_yielded:
                continue
            yield _to_sse(event)
            last_yielded = event.seq
    finally:
        container.bus.unsubscribe(sub)


@router.get("/events")
async def stream_events(
    request: Request,
    job_id: str | None = None,
    batch_id: str | None = None,
    types: str | None = None,
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID")] = None,
) -> EventSourceResponse:
    container = _container(request)
    type_list = [t for t in (types or "").split(",") if t]
    sub = container.bus.subscribe(job_id=job_id, batch_id=batch_id, types=type_list or None)
    generator = _event_generator(
        container, sub, job_id=job_id, batch_id=batch_id,
        types=type_list or None, last_event_id=last_event_id or 0,
    )
    return EventSourceResponse(
        generator,
        ping=int(container.settings.sse_heartbeat_seconds),
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
