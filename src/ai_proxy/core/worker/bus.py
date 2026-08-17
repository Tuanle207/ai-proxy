"""EventBus: persist-then-fanout with bounded subscriber queues (§3.3).

Every event is written to `job_events` first (assigned a monotonic `seq`), then fanned out to
matching subscribers. Subscriber queues are bounded: on overflow the slow consumer is dropped
with a `stream.overflow` event, never blocking the producer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ai_proxy.core.db.engine import utc_now
from ai_proxy.core.db.events_repo import EventRecord, EventsRepo

_OVERFLOW_EVENT_TYPE = "stream.overflow"


@dataclass(eq=False)
class Subscription:
    queue: asyncio.Queue[EventRecord]
    job_id: str | None = None
    batch_id: str | None = None
    types: frozenset[str] = field(default_factory=frozenset)

    def matches(self, event: EventRecord) -> bool:
        if self.job_id is not None and event.job_id != self.job_id:
            return False
        if self.batch_id is not None and event.batch_id != self.batch_id:
            return False
        if self.types and event.type not in self.types:
            return False
        return True


class EventBus:
    def __init__(self, events: EventsRepo, *, maxsize: int = 256):
        self._events = events
        self._maxsize = maxsize
        self._subscribers: set[Subscription] = set()

    async def publish(
        self,
        *,
        type: str,
        job_id: str | None = None,
        batch_id: str | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        seq = await self._events.append(
            job_id=job_id, batch_id=batch_id, type=type, status=status, payload=payload
        )
        event = EventRecord(
            seq=seq,
            job_id=job_id,
            batch_id=batch_id,
            type=type,
            status=status,
            payload=payload or {},
            created_at=utc_now(),
        )
        overflowed: list[Subscription] = []
        for sub in list(self._subscribers):
            if not sub.matches(event):
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                overflowed.append(sub)
        for sub in overflowed:
            self._subscribers.discard(sub)
            self._send_overflow(sub)
        return seq

    def _send_overflow(self, sub: Subscription) -> None:
        event = EventRecord(
            seq=-1,
            job_id=None,
            batch_id=None,
            type=_OVERFLOW_EVENT_TYPE,
            status=None,
            payload={"message": "slow consumer dropped: subscriber queue overflow"},
            created_at=utc_now(),
        )
        try:
            sub.queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    def subscribe(
        self,
        *,
        job_id: str | None = None,
        batch_id: str | None = None,
        types: list[str] | None = None,
    ) -> Subscription:
        sub = Subscription(
            queue=asyncio.Queue(maxsize=self._maxsize),
            job_id=job_id,
            batch_id=batch_id,
            types=frozenset(types) if types else frozenset(),
        )
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._subscribers.discard(sub)


async def publish_queue_stats_loop(
    bus: EventBus,
    get_stats: Callable[[], Awaitable[dict[str, Any]]],
    *,
    interval: float,
    stop_event: asyncio.Event,
) -> None:
    """Periodically publish a `queue.stats` event (depth, free slots, throughput, ETA)."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            continue
        except TimeoutError:
            pass
        await bus.publish(type="queue.stats", payload=await get_stats())
