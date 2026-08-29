"""Event bus.

One `emit()` call fans out to three places:
  1. the durable ledger (Firestore) — so the audit trail survives restarts
  2. Pub/Sub — so background workers and other services react
  3. in-process SSE subscribers — so the console updates instantly

Decoupling matters here: the orchestrator publishes work and never waits for
a hunter. That is what lets a run span nine weeks across many Cloud Run
instances instead of one long-lived process.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from app.config import settings
from app.core.models import FleetEvent
from app.core.store import EVENTS, get_store

log = logging.getLogger("atlas.events")


class Broadcaster:
    """Fan-out to every connected SSE client, with backpressure safety."""

    def __init__(self, maxsize: int = 200) -> None:
        self._subscribers: set[asyncio.Queue[FleetEvent]] = set()
        self._maxsize = maxsize
        self._recent: list[FleetEvent] = []

    def subscribe(self) -> asyncio.Queue[FleetEvent]:
        q: asyncio.Queue[FleetEvent] = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[FleetEvent]) -> None:
        self._subscribers.discard(q)

    def publish(self, event: FleetEvent) -> None:
        self._recent.insert(0, event)
        del self._recent[120:]
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # A slow client must never stall the fleet. Drop it.
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    @property
    def recent(self) -> list[FleetEvent]:
        return list(self._recent)

    @property
    def client_count(self) -> int:
        return len(self._subscribers)


broadcaster = Broadcaster()


class PubSubPublisher:
    """Thin wrapper; no-ops cleanly when Pub/Sub is unavailable."""

    def __init__(self) -> None:
        self._publisher = None
        self._topic = None
        if not settings.is_cloud:
            return
        try:
            from google.cloud import pubsub_v1

            self._publisher = pubsub_v1.PublisherClient()
            self._topic = self._publisher.topic_path(settings.project_id, settings.topic_events)
            log.info("pubsub: publishing to %s", self._topic)
        except Exception as exc:  # pragma: no cover
            log.warning("pubsub unavailable (%s); events stay in-process", exc)

    def publish(self, event: FleetEvent) -> None:
        if not self._publisher:
            return
        try:
            self._publisher.publish(
                self._topic,
                json.dumps(event.model_dump(mode="json")).encode(),
                kind=event.kind,
                agent=event.agent,
            )
        except Exception as exc:  # pragma: no cover
            log.warning("pubsub publish failed: %s", exc)


_pubsub: PubSubPublisher | None = None


def _get_pubsub() -> PubSubPublisher:
    global _pubsub
    if _pubsub is None:
        _pubsub = PubSubPublisher()
    return _pubsub


async def emit(
    agent: str,
    kind: str,
    message: str,
    *,
    control_id: str | None = None,
    severity: str = "info",
    trace_id: str = "",
    **meta,
) -> FleetEvent:
    """Record one thing the fleet did. This is the product's heartbeat."""
    event = FleetEvent(
        agent=agent,
        kind=kind,
        message=message,
        control_id=control_id,
        severity=severity,  # type: ignore[arg-type]
        trace_id=trace_id,
        meta=meta,
    )
    await get_store().put(EVENTS, event)
    broadcaster.publish(event)
    _get_pubsub().publish(event)
    log.info("[%s] %s %s", agent, kind, message)
    return event


async def sse_stream(replay: int = 25) -> AsyncIterator[str]:
    """Server-sent events for the console. Replays recent history on connect."""
    q = broadcaster.subscribe()
    try:
        for event in reversed(broadcaster.recent[:replay]):
            yield f"data: {event.model_dump_json()}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=20.0)
                yield f"data: {event.model_dump_json()}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        broadcaster.unsubscribe(q)
