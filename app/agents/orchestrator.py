"""Orchestrator — plans the audit window and drives the fleet.

Uses all three ADK orchestration patterns, each where it actually fits:

  * PARALLEL   — the five domain hunters fan out; they share nothing.
  * SEQUENTIAL — per control: hunt → judge → file. Order is load-bearing.
  * LOOP       — chase → wait → recheck, until answered or escalated out.

Work is dispatched as idempotent tasks. A redelivered Pub/Sub message for a
completed step is a no-op, which is the difference between a resumable agent
and one that files the same evidence twice.
"""
from __future__ import annotations

import asyncio
import logging

from app.agents import chaser, hunters
from app.agents.judge import rule
from app.config import settings
from app.core import identity, registry
from app.core.events import emit
from app.core.models import (
    Control,
    ControlStatus,
    Domain,
    RunSummary,
    Verdict,
    new_id,
    now,
)
from app.core.store import (
    CONTROLS,
    RUNS,
    claim_task,
    complete_task,
    get_store,
    recompute_summary,
)
from app.core.telemetry import new_trace_id, span

log = logging.getLogger("atlas.orchestrator")

class Orchestrator:
    """Owns a run. One instance per audit window."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or new_id("run")
        self._halted = False

    # ---------------------------------------------------------- planning
    async def plan(self) -> dict[Domain, list[Control]]:
        """Group outstanding controls by domain so hunters can fan out."""
        store = get_store()
        controls: list[Control] = await store.list(CONTROLS, limit=5000)
        todo = [
            c
            for c in controls
            if c.status
            in (ControlStatus.IDLE, ControlStatus.STALE, ControlStatus.FAILED, ControlStatus.WORKING)
        ]
        buckets: dict[Domain, list[Control]] = {d: [] for d in hunters.hunter_domains()}
        for c in todo:
            buckets[c.domain].append(c)
        return buckets

    # --------------------------------------------------------- execution
    async def process_control(self, control: Control, trace_id: str) -> None:
        """Sequential pipeline for one control. Every step is idempotent."""
        store = get_store()

        task = await claim_task(self.run_id, control.id, "hunt", "orchestrator")
        if task is None:
            log.debug("skip %s — already processed in this run", control.id)
            return

        try:
            control.status = ControlStatus.WORKING
            control.updated_at = now()
            await store.put(CONTROLS, control)

            # 1. hunt
            await hunters.hunt(control, self.run_id, trace_id)
            control = await store.get(CONTROLS, control.id) or control

            # 2. judge
            ruling = await rule(control, self.run_id, trace_id)
            control.ruling = ruling

            # 3. act on the verdict
            if ruling.verdict is Verdict.SATISFIED:
                control.status = ControlStatus.VERIFIED
            elif ruling.verdict is Verdict.NEEDS_HUMAN:
                await store.put(CONTROLS, control)
                await chaser.open_handoff(control, ruling, trace_id)
                control = await store.get(CONTROLS, control.id) or control
            else:
                control.status = ControlStatus.FAILED

            control.updated_at = now()
            control.updated_by = "orchestrator"
            await store.put(CONTROLS, control)
            await complete_task(task)

        except Exception as exc:  # noqa: BLE001 - a failed control must not kill the run
            log.exception("control %s failed", control.id)
            await complete_task(task, error=str(exc))
            await emit(
                "orchestrator",
                "error",
                f"{control.id} failed: {exc}",
                control_id=control.id,
                severity="alert",
                trace_id=trace_id,
            )

    async def _run_domain(self, domain: Domain, controls: list[Control], trace_id: str) -> None:
        for control in controls:
            if self._halted:
                return
            await self.process_control(control, trace_id)

    # -------------------------------------------------------------- sweep
    async def run_sweep(self, limit_per_domain: int = 3) -> RunSummary:
        """One evidence sweep across the fleet. This is what the demo triggers."""
        trace_id = new_trace_id()
        store = get_store()

        summary: RunSummary | None = await store.get(RUNS, self.run_id)
        if summary is None:
            summary = RunSummary(
                run_id=self.run_id, started_at=now(), budget_usd=settings.run_budget_usd
            )
            await store.put(RUNS, summary)

        with identity.assume("orchestrator"):
            await registry.record_invocation("orchestrator")
            with span("orchestrator.plan", agent="orchestrator", trace_id=trace_id) as sp:
                buckets = await self.plan()
                planned = sum(len(v[:limit_per_domain]) for v in buckets.values())
                sp.attributes["controls_planned"] = planned

            await emit(
                "orchestrator",
                "planned",
                f"dispatching {planned} control(s) across {len(buckets)} domains",
                trace_id=trace_id,
            )

            # budget governor — refuse to start work we cannot afford
            projected = (
                summary.cost_usd
                + planned * settings.estimated_cost_per_control_usd
            )
            if projected > summary.budget_usd:
                self._halted = True
                summary.halted = True
                await store.put(RUNS, summary)
                await emit(
                    "orchestrator",
                    "halted",
                    f"HALTED_ON_BUDGET — projected ${projected:.2f} exceeds ${summary.budget_usd:.2f}",
                    severity="alert",
                    trace_id=trace_id,
                )
                return summary

            # PARALLEL: domains are independent, so run them concurrently
            await asyncio.gather(
                *(
                    self._run_domain(domain, controls[:limit_per_domain], trace_id)
                    for domain, controls in buckets.items()
                    if controls
                )
            )

            summary = await recompute_summary(self.run_id)
            summary.cost_usd = round(
                summary.cost_usd
                + planned * settings.estimated_cost_per_control_usd,
                4,
            )
            await store.put(RUNS, summary)

            await emit(
                "orchestrator",
                "swept",
                f"sweep done · {summary.controls_verified}/{summary.controls_total} verified · "
                f"{summary.autonomy_pct}% autonomous · ${summary.cost_usd:.4f} spent",
                trace_id=trace_id,
            )
        return summary

    # ------------------------------------------------------------- daemon
    async def background_loop(self, interval_seconds: int = 900) -> None:
        """Long-horizon execution.

        On Cloud Run this is replaced by Cloud Scheduler hitting /internal/sweep,
        so no instance needs to stay warm for nine weeks. This loop exists for
        local runs and for the demo.
        """
        while True:
            try:
                await self.run_sweep()
                await chaser.sweep(self.run_id, new_trace_id())
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover
                log.exception("background sweep failed; continuing")
            await asyncio.sleep(interval_seconds)


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator(run_id="run-2026-q3")
    return _orchestrator
