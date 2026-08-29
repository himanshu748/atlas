"""Chaser and Drift Sentinel — the two agents that make this a fleet.

Chaser owns every human interaction. It opens exactly one handoff per
blocking question, dedupes against open handoffs so an owner is never asked
twice for the same thing, and walks an escalation ladder so the fleet never
deadlocks waiting on a person.

Drift Sentinel is what makes ATLAS alive rather than a batch job. It runs on
Cloud Scheduler, recomputes freshness, and reopens controls that were green
and no longer are — autonomously, without a human noticing the regression
first.
"""
from __future__ import annotations

import logging

from app.core import identity
from app.core.events import emit
from app.core.models import (
    Control,
    ControlStatus,
    Handoff,
    Ruling,
    Verdict,
    now,
)
from app.core.store import CONTROLS, EVIDENCE, HANDOFFS, get_store
from app.core.telemetry import span
from app.config import settings

log = logging.getLogger("atlas.chaser")


# ------------------------------------------------------------------ chaser
async def open_handoff(control: Control, ruling: Ruling, trace_id: str) -> Handoff | None:
    """Ask a human exactly once, with everything they need to answer in seconds."""
    store = get_store()
    open_handoffs: list[Handoff] = await store.list(HANDOFFS, limit=1000)

    # Dedupe: an open handoff for this control means the human already has it.
    for h in open_handoffs:
        if h.control_id == control.id and h.is_open:
            log.info("handoff already open for %s (%s) — not re-asking", control.id, h.id)
            return None

    with identity.assume("chaser"):
        handoff = Handoff(
            control_id=control.id,
            question=ruling.blocking_question or f"{control.id} needs a human decision.",
            reasoning=ruling.reasoning,
            candidate_evidence=ruling.cited_evidence,
            recommendation=(
                "Approve if this matches existing precedent; reject with a reason "
                "and the fleet will record it as a new requirement."
            ),
            sla_hours=settings.max_handoff_hours,
        )
        await store.put(HANDOFFS, handoff)

        control.status = ControlStatus.WAITING
        control.handoff_id = handoff.id
        control.updated_at = now()
        control.updated_by = "chaser"
        await store.put(CONTROLS, control)

        with span("chaser.notify", agent="chaser", trace_id=trace_id, control=control.id):
            await _notify(control, handoff)

        await emit(
            "chaser",
            "nudged",
            f"opened {handoff.id} for {control.id} · owner {control.owner} (touch 1/3)",
            control_id=control.id,
            severity="warn",
            trace_id=trace_id,
        )
    return handoff


async def _notify(control: Control, handoff: Handoff) -> None:
    """Send the nudge. Slack when configured, otherwise the in-app inbox."""
    if not settings.slack_token:
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {settings.slack_token}"},
                json={
                    "channel": f"@{control.owner}",
                    "text": f"*{control.id}* needs your call: {handoff.question}",
                },
            )
    except Exception as exc:  # pragma: no cover
        log.warning("slack notify failed: %s", exc)


async def answer_handoff(handoff_id: str, answer: str, reason: str = "") -> Handoff | None:
    """Record a human decision and unblock the control.

    A rejection is not a failure — it is a new organisational requirement, so
    we write it to Memory Bank. That is the loop that makes next year cheaper.
    """
    store = get_store()
    handoff: Handoff | None = await store.get(HANDOFFS, handoff_id)
    if handoff is None or not handoff.is_open:
        return handoff

    handoff.answered_at = now()
    handoff.answer = "approved" if answer == "approved" else "rejected"
    handoff.answer_reason = reason
    await store.put(HANDOFFS, handoff)

    control: Control | None = await store.get(CONTROLS, handoff.control_id)
    if control:
        control.human_touches += 1
        control.handoff_id = None
        control.status = (
            ControlStatus.VERIFIED if handoff.answer == "approved" else ControlStatus.FAILED
        )
        control.updated_at = now()
        control.updated_by = "human"
        await store.put(CONTROLS, control)

    from app.core.memory import memory_bank

    if handoff.answer == "approved":
        await memory_bank.remember(
            f"{handoff.control_id}: {handoff.question} — approved by the compliance lead. "
            f"Treat as precedent.",
            subject=handoff.control_id,
            confidence=0.9,
        )
    elif reason:
        await memory_bank.remember(
            f"{handoff.control_id}: rejected — {reason}. Do not propose this again.",
            subject=handoff.control_id,
            confidence=0.9,
        )

    await emit(
        "chaser",
        "answered",
        f"{handoff.id} {handoff.answer} by human · {handoff.control_id} unblocked",
        control_id=handoff.control_id,
    )
    return handoff


async def escalate_overdue() -> int:
    """Walk the escalation ladder. The fleet never deadlocks on a person."""
    store = get_store()
    handoffs: list[Handoff] = await store.list(HANDOFFS, limit=1000)
    escalated = 0

    for h in handoffs:
        if not h.is_open or h.hours_remaining > 0:
            continue
        h.stage += 1
        h.opened_at = now()  # restart the clock at the next rung
        await store.put(HANDOFFS, h)
        escalated += 1

        if h.stage >= 3:
            control = await store.get(CONTROLS, h.control_id)
            if control:
                control.status = ControlStatus.FAILED
                control.updated_by = "chaser"
                await store.put(CONTROLS, control)
            await emit(
                "chaser",
                "at_risk",
                f"{h.control_id} marked AT_RISK — no human response after 3 escalations",
                control_id=h.control_id,
                severity="alert",
            )
        else:
            await emit(
                "chaser",
                "escalated",
                f"{h.id} escalated to stage {h.stage}/3 for {h.control_id}",
                control_id=h.control_id,
                severity="warn",
            )
    return escalated


# ---------------------------------------------------------------- sentinel
async def sweep(run_id: str, trace_id: str) -> dict[str, int]:
    """Weekly freshness + regression sweep. Reopens work without being asked."""
    store = get_store()
    controls: list[Control] = await store.list(CONTROLS, limit=5000)
    all_evidence = {e.id: e for e in await store.list(EVIDENCE, limit=5000)}

    went_stale = 0
    regressed = 0

    with identity.assume("sentinel"):
        for control in controls:
            evidence = [all_evidence[i] for i in control.evidence_ids if i in all_evidence]
            if not evidence:
                continue
            stale = [e for e in evidence if e.is_stale]
            if stale and control.status == ControlStatus.VERIFIED:
                control.status = ControlStatus.STALE
                control.updated_at = now()
                control.updated_by = "sentinel"
                await store.put(CONTROLS, control)
                went_stale += 1
                await emit(
                    "sentinel",
                    "stale",
                    f"{control.id} freshness SLA breached ({stale[0].age_days}d) → STALE",
                    control_id=control.id,
                    severity="warn",
                    trace_id=trace_id,
                )
            elif (
                control.status == ControlStatus.VERIFIED
                and control.ruling
                and control.ruling.verdict is not Verdict.SATISFIED
            ):
                control.status = ControlStatus.FAILED
                await store.put(CONTROLS, control)
                regressed += 1

        escalated = await escalate_overdue()

        await emit(
            "sentinel",
            "swept",
            f"sweep complete · {len(controls)} controls · {went_stale} stale · "
            f"{regressed} regressed · {escalated} escalated",
            trace_id=trace_id,
        )

    return {"stale": went_stale, "regressed": regressed, "escalated": escalated}
