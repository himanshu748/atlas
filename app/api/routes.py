"""HTTP surface.

Read endpoints back the console; write endpoints are the only way state
changes from outside the fleet. `/internal/*` is what Cloud Scheduler calls,
kept separate so it can be locked down with an OIDC audience in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.agents import chaser
from app.agents.assembler import build_package
from app.agents.orchestrator import get_orchestrator
from app.config import settings
from app.core import registry
from app.core.events import broadcaster, sse_stream
from app.core.memory import memory_bank
from app.core.models import Control, Evidence, Handoff
from app.core.store import (
    AGENTS,
    ARMOR,
    CONTROLS,
    EVIDENCE,
    HANDOFFS,
    MEMORIES,
    get_store,
    recompute_summary,
)
from app.core.telemetry import new_trace_id, traces

log = logging.getLogger("atlas.api")
router = APIRouter()

RUN_ID = "run-2026-q3"


# ------------------------------------------------------------------ fleet
@router.get("/api/fleet")
async def fleet_state(request: Request):
    """Everything the Fleet Command screen needs in one round trip."""
    store = get_store()
    runtime_settings = getattr(request.app.state, "settings", settings)
    summary = await recompute_summary(RUN_ID, persist=not runtime_settings.public_demo)
    controls: list[Control] = await store.list(CONTROLS, limit=5000)
    handoffs: list[Handoff] = await store.list(HANDOFFS, limit=1000)

    by_status: dict[str, int] = {}
    for c in controls:
        by_status[c.status.value] = by_status.get(c.status.value, 0) + 1

    return {
        "run_id": summary.run_id,
        "runtime_mode": "local" if runtime_settings.public_demo else runtime_settings.mode,
        "public_demo": runtime_settings.public_demo,
        "read_only": runtime_settings.public_demo,
        "data_profile": "seeded-fixtures" if runtime_settings.public_demo else "runtime-ledger",
        "cloud_location": runtime_settings.location if runtime_settings.is_cloud else None,
        "model": runtime_settings.model_fast,
        "model_backend": runtime_settings.model_backend,
        "readiness_pct": summary.readiness_pct,
        "autonomy_pct": summary.autonomy_pct,
        "uptime_seconds": summary.uptime_seconds,
        "controls_total": summary.controls_total,
        "controls_verified": summary.controls_verified,
        "handoffs_open": summary.handoffs_open,
        "cost_usd": summary.cost_usd,
        "budget_usd": summary.budget_usd,
        "halted": summary.halted,
        "dlq_depth": summary.dlq_depth,
        "by_status": by_status,
        "agents": len(await store.list(AGENTS, limit=100)),
        "sse_clients": broadcaster.client_count,
        "coverage": [
            {"id": c.id, "group": c.group, "status": c.status.value} for c in sorted(controls, key=lambda x: x.id)
        ],
        "handoffs": [
            {**h.model_dump(mode="json"), "hours_remaining": round(h.hours_remaining, 1)}
            for h in handoffs if h.is_open
        ][:5],
    }


@router.get("/api/events")
async def recent_events(limit: int = Query(40, le=200)):
    return [e.model_dump(mode="json") for e in broadcaster.recent[:limit]]


@router.get("/api/stream")
async def stream():
    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------- controls
@router.get("/api/controls")
async def list_controls(status: str | None = None):
    controls: list[Control] = await get_store().list(CONTROLS, limit=5000)
    if status and status != "all":
        controls = [c for c in controls if c.status.value == status]
    return [
        {
            **c.model_dump(mode="json"),
            "evidence_count": c.evidence_count,
            "coverage": round(c.coverage, 3),
            "closed_autonomously": c.closed_autonomously,
        }
        for c in sorted(controls, key=lambda x: x.id)
    ]


@router.get("/api/controls/{control_id}")
async def get_control(control_id: str):
    store = get_store()
    control: Control | None = await store.get(CONTROLS, control_id)
    if control is None:
        raise HTTPException(404, f"no control {control_id}")

    all_evidence: list[Evidence] = await store.list(EVIDENCE, limit=5000)
    evidence = [e for e in all_evidence if e.id in set(control.evidence_ids)]
    handoff = await store.get(HANDOFFS, control.handoff_id) if control.handoff_id else None

    return {
        "control": control.model_dump(mode="json"),
        "evidence": [
            {**e.model_dump(mode="json"), "age_days": e.age_days, "is_stale": e.is_stale}
            for e in sorted(evidence, key=lambda x: x.collected_at, reverse=True)
        ],
        "handoff": handoff.model_dump(mode="json") if handoff else None,
        "custody": [
            {"hop": "source system", "value": evidence[0].source_system if evidence else "—"},
            {"hop": "agent identity", "value": evidence[0].agent_identity if evidence else "—"},
            {"hop": "armor verdict", "value": evidence[0].armor_verdict.value if evidence else "—"},
            {"hop": "sha256", "value": (evidence[0].sha256[:16] + "…") if evidence else "—"},
            {"hop": "evidence ledger", "value": "recorded" if evidence else "—"},
        ],
    }


class SweepRequest(BaseModel):
    limit_per_domain: int = 3


@router.post("/api/sweep")
async def run_sweep(req: SweepRequest):
    """Trigger an evidence sweep. This is the button pressed in the demo."""
    summary = await get_orchestrator().run_sweep(limit_per_domain=req.limit_per_domain)
    return {
        "run_id": summary.run_id,
        "readiness_pct": summary.readiness_pct,
        "autonomy_pct": summary.autonomy_pct,
        "cost_usd": summary.cost_usd,
        "halted": summary.halted,
    }


# --------------------------------------------------------------- handoffs
@router.get("/api/handoffs")
async def list_handoffs(include_closed: bool = False):
    handoffs: list[Handoff] = await get_store().list(HANDOFFS, limit=1000)
    if not include_closed:
        handoffs = [h for h in handoffs if h.is_open]
    return [
        {**h.model_dump(mode="json"), "hours_remaining": round(h.hours_remaining, 1)}
        for h in sorted(handoffs, key=lambda x: x.opened_at, reverse=True)
    ]


class AnswerRequest(BaseModel):
    answer: str  # "approved" | "rejected"
    reason: str = ""


@router.post("/api/handoffs/{handoff_id}/answer")
async def answer(handoff_id: str, req: AnswerRequest):
    handoff = await chaser.answer_handoff(handoff_id, req.answer, req.reason)
    if handoff is None:
        raise HTTPException(404, f"no open handoff {handoff_id}")
    await recompute_summary(RUN_ID)
    return handoff.model_dump(mode="json")


# --------------------------------------------------------------- registry
@router.get("/api/agents")
async def list_agents(capability: str | None = None):
    cards = await registry.search(capability) if capability else await get_store().list(AGENTS, limit=100)
    return [c.model_dump(mode="json") for c in sorted(cards, key=lambda x: x.name)]


# --------------------------------------------------------------- security
@router.get("/api/armor")
async def armor_log(limit: int = Query(50, le=200)):
    verdicts = await get_store().list(ARMOR, limit=500)
    verdicts = sorted(verdicts, key=lambda v: v.at, reverse=True)[:limit]
    counts = {"pass": 0, "redacted": 0, "blocked": 0}
    for v in await get_store().list(ARMOR, limit=500):
        counts[v.action.value] = counts.get(v.action.value, 0) + 1
    return {
        "counts": counts,
        "screened": sum(counts.values()),
        "verdicts": [v.model_dump(mode="json") for v in verdicts],
    }


# ----------------------------------------------------------------- memory
@router.get("/api/memories")
async def list_memories():
    memories = await get_store().list(MEMORIES, limit=500)
    return [
        m.model_dump(mode="json")
        for m in sorted(memories, key=lambda x: (x.confidence, x.reinforced), reverse=True)
    ]


class RecallRequest(BaseModel):
    query: str
    subject: str = ""


@router.post("/api/memories/recall")
async def recall(req: RecallRequest):
    found = await memory_bank.recall(req.query, subject=req.subject)
    return [m.model_dump(mode="json") for m in found]


# ----------------------------------------------------------------- traces
@router.get("/api/traces")
async def list_traces():
    out = []
    for tid in traces.list_ids():
        spans = traces.get(tid)
        out.append(
            {
                "trace_id": tid,
                "spans": len(spans),
                "duration_ms": round(sum(s.duration_ms for s in spans), 1),
                "agents": sorted({s.agent for s in spans}),
            }
        )
    return out


@router.get("/api/traces/{trace_id}")
async def get_trace(trace_id: str):
    spans = traces.get(trace_id)
    if not spans:
        raise HTTPException(404, f"no trace {trace_id}")
    return {"trace_id": trace_id, "spans": [s.to_dict() for s in spans]}


# ---------------------------------------------------------------- package
@router.post("/api/package")
async def package():
    manifest = await build_package(RUN_ID, new_trace_id())
    return JSONResponse(
        content=manifest,
        headers={
            "Content-Disposition": 'attachment; filename="manifest.json"',
            "Cache-Control": "no-store",
        },
    )


# ------------------------------------------------------------- multimodal
@router.get("/api/briefing")
async def briefing():
    """The 45-second spoken standup. Text always, MP3 when TTS is available."""
    from app.agents.multimodal import daily_briefing

    return await daily_briefing(new_trace_id())


@router.post("/api/controls/{control_id}/visual-evidence")
async def visual_evidence(control_id: str, file: UploadFile = File(...)):
    """Upload a screenshot, PDF or screen recording as evidence for a control.

    Half of real audit evidence is a picture of an admin console. The model
    extracts a structured claim; the source media stays pinned beside it so a
    human can check what was read.
    """
    from app.agents.multimodal import parse_visual_evidence

    control: Control | None = await get_store().get(CONTROLS, control_id)
    if control is None:
        raise HTTPException(404, f"no control {control_id}")

    kind = (
        "pdf" if (file.content_type or "").endswith("pdf")
        else "video" if (file.content_type or "").startswith("video")
        else "image"
    )
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "artifact exceeds 20MB")

    claim = await parse_visual_evidence(
        data, kind, control, agent=f"hunter/{control.domain.value}", trace_id=new_trace_id()
    )
    return {"control_id": control_id, "kind": kind, "bytes": len(data), **claim.model_dump()}


# --------------------------------------------------------------- internal
@router.post("/internal/sweep")
async def internal_sweep():
    """Cloud Scheduler target. Replaces keeping an instance warm for 9 weeks."""
    summary = await get_orchestrator().run_sweep()
    sweep_result = await chaser.sweep(RUN_ID, new_trace_id())
    return {"readiness_pct": summary.readiness_pct, **sweep_result}


@router.get("/api/health")
@router.get("/healthz")
async def healthz():
    return {"status": "ok"}
