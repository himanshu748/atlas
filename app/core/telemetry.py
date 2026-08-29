"""Observability.

The auditor audits us. Reasoning-chain traces are a product surface, not just
ops telemetry, so spans are captured into the ledger as well as exported to
Cloud Trace. Every span carries the acting agent's SPIFFE identity, which is
what turns a latency waterfall into a chain-of-custody document.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.config import settings

log = logging.getLogger("atlas.telemetry")

_tracer = None


def init_tracing() -> None:
    """Wire OpenTelemetry to Cloud Trace when running on GCP."""
    global _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": "atlas-fleet"})
        provider = TracerProvider(resource=resource)

        if settings.is_cloud:
            try:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

                provider.add_span_processor(
                    BatchSpanProcessor(CloudTraceSpanExporter(project_id=settings.project_id))
                )
                log.info("tracing: exporting to Cloud Trace")
            except Exception as exc:  # pragma: no cover
                log.warning("cloud trace exporter unavailable: %s", exc)

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("atlas")
    except Exception as exc:  # pragma: no cover
        log.warning("tracing disabled: %s", exc)


@dataclass
class Span:
    name: str
    agent: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid4().hex[:8])
    parent_id: str | None = None
    start_ms: float = 0.0
    duration_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent": self.agent,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "duration_ms": round(self.duration_ms, 1),
            "attributes": self.attributes,
        }


class TraceBuffer:
    """Recent traces, kept in memory for the Trace Explorer screen."""

    def __init__(self, cap: int = 40) -> None:
        self._traces: dict[str, list[Span]] = {}
        self._order: list[str] = []
        self._cap = cap

    def add(self, span: Span) -> None:
        if span.trace_id not in self._traces:
            self._traces[span.trace_id] = []
            self._order.insert(0, span.trace_id)
            for stale in self._order[self._cap:]:
                self._traces.pop(stale, None)
            del self._order[self._cap:]
        self._traces[span.trace_id].append(span)

    def get(self, trace_id: str) -> list[Span]:
        return self._traces.get(trace_id, [])

    def latest(self) -> tuple[str, list[Span]] | None:
        if not self._order:
            return None
        tid = self._order[0]
        return tid, self._traces[tid]

    def list_ids(self) -> list[str]:
        return list(self._order)


traces = TraceBuffer()


def new_trace_id() -> str:
    return uuid4().hex[:16]


@contextmanager
def span(name: str, *, agent: str, trace_id: str, parent_id: str | None = None, **attrs):
    """Record one step of reasoning. Doubles as an OTel span when available."""
    s = Span(name=name, agent=agent, trace_id=trace_id, parent_id=parent_id, attributes=dict(attrs))
    s.start_ms = time.perf_counter() * 1000

    from app.core.identity import current as current_identity

    identity = current_identity()
    if identity:
        s.attributes["spiffe_id"] = identity.spiffe_id

    otel_cm = None
    if _tracer is not None:
        otel_cm = _tracer.start_as_current_span(name)
        otel_span = otel_cm.__enter__()
        for k, v in s.attributes.items():
            try:
                otel_span.set_attribute(k, v)
            except Exception:
                pass
    try:
        yield s
    finally:
        s.duration_ms = time.perf_counter() * 1000 - s.start_ms
        traces.add(s)
        if otel_cm is not None:
            try:
                otel_cm.__exit__(None, None, None)
            except Exception:
                pass
