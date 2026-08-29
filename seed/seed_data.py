"""Seed the ledger.

Creates the 64-control ledger, the prior-audit memories, and the registry
cards. Optionally backdates a nine-week history so the console shows a fleet
that has been running for weeks rather than seconds — which is the whole
point of the product and impossible to demonstrate honestly in a live 4-minute
video otherwise.

The backfill only ever writes synthetic evidence; nothing it produces is
presented as having come from a live system.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta

from app.config import settings
from app.core import registry
from app.core.memory import memory_bank
from app.core.models import (
    Control,
    ControlStatus,
    Evidence,
    FleetEvent,
    RunSummary,
    now,
)
from app.core.store import CONTROLS, EVENTS, EVIDENCE, RUNS, get_store
from seed.soc2_controls import CONTROLS as CONTROL_DEFS
from seed.soc2_controls import OWNERS, PRIOR_MEMORIES

log = logging.getLogger("atlas.seed")

_BACKFILL_LINES = [
    ("hunter/iam", "collected", "fetched {n} IAM bindings ▸ {f} flagged"),
    ("hunter/sdlc", "collected", "scanned {n} PRs ▸ review enforcement verified"),
    ("hunter/infra", "collected", "CMEK verified on {f}/{f} storage buckets"),
    ("judge", "ruled", "{c} → SATISFIED"),
    ("judge", "ruled", "{c} → INSUFFICIENT · evidence does not cover the full period"),
    ("chaser", "nudged", "nudged owner re: {c} (touch 1/3)"),
    ("sentinel", "swept", "weekly sweep · 64 controls · {f} regressions"),
    ("assembler", "packaged", "manifest updated · {n} artifacts hashed"),
]


async def seed_controls() -> int:
    store = get_store()
    for cid, name, domain, text, required, fresh in CONTROL_DEFS:
        existing = await store.get(CONTROLS, cid)
        if existing:
            continue
        await store.put(
            CONTROLS,
            Control(
                id=cid,
                group=cid.split(".")[0],
                name=name,
                text=text,
                domain=domain,
                owner=OWNERS[domain],
                evidence_required=required,
                freshness_days=fresh,
                status=ControlStatus.IDLE,
            ),
        )
    log.info("seeded %d controls", len(CONTROL_DEFS))
    return len(CONTROL_DEFS)


async def seed_memories() -> int:
    for subject, text, confidence in PRIOR_MEMORIES:
        await memory_bank.remember(
            text,
            subject=subject,
            source_run="run-2025-audit",
            confidence=confidence,
        )
    log.info("seeded %d prior memories", len(PRIOR_MEMORIES))
    return len(PRIOR_MEMORIES)


async def backfill_history(weeks: int = 9, seed: int = 7) -> int:
    """Write a plausible nine-week operating history for the time machine."""
    rng = random.Random(seed)
    store = get_store()
    controls: list[Control] = await store.list(CONTROLS, limit=200)
    if not controls:
        return 0

    start = now() - timedelta(weeks=weeks)
    written = 0

    # A realistic distribution: most controls green, a handful in each other state.
    for i, control in enumerate(controls):
        r = rng.random()
        if r < 0.72:
            status = ControlStatus.VERIFIED
            touches = 0 if rng.random() < 0.94 else 1
        elif r < 0.80:
            status = ControlStatus.WORKING
            touches = 0
        elif r < 0.87:
            status = ControlStatus.WAITING
            touches = 1
        elif r < 0.93:
            status = ControlStatus.STALE
            touches = 0
        elif r < 0.97:
            status = ControlStatus.FAILED
            touches = 1
        else:
            status = ControlStatus.IDLE
            touches = 0

        control.status = status
        control.human_touches = touches
        control.updated_at = start + timedelta(days=rng.uniform(1, weeks * 7 - 1))

        if status is not ControlStatus.IDLE:
            for k in range(control.evidence_required):
                age = rng.uniform(2, 110 if status is ControlStatus.STALE else 40)
                ev = Evidence(
                    control_id=control.id,
                    name=f"{control.domain.value}-evidence-{control.id.lower().replace('.', '-')}-{k+1}.json",
                    kind="json",
                    source_system=f"{control.domain.value}.system",
                    collected_by=f"hunter/{control.domain.value}",
                    agent_identity=f"spiffe://{settings.trust_domain}/agent/hunter-{control.domain.value}",
                    collected_at=now() - timedelta(days=age),
                    freshness_days=control.freshness_days,
                    sha256=Evidence.hash_payload(f"{control.id}-{k}-{seed}"),
                    size_bytes=rng.randint(1200, 480000),
                    summary=f"Synthetic backfill artifact {k+1} for {control.id}.",
                    payload_ref=f"local://backfill/{control.id}/{k+1}",
                )
                await store.put(EVIDENCE, ev)
                control.evidence_ids.append(ev.id)
                written += 1

        await store.put(CONTROLS, control)

    # A trickle of historical events so the stream is not empty on first load.
    for d in range(weeks * 7):
        for _ in range(rng.randint(0, 2)):
            agent, kind, template = rng.choice(_BACKFILL_LINES)
            control = rng.choice(controls)
            event = FleetEvent(
                at=start + timedelta(days=d, hours=rng.uniform(0, 23)),
                agent=agent,
                kind=kind,
                message=template.format(
                    n=rng.randint(120, 1400), f=rng.randint(0, 41), c=control.id
                ),
                control_id=control.id,
            )
            await store.put(EVENTS, event)

    log.info("backfilled %d weeks of history (%d artifacts)", weeks, written)
    return written


async def seed_all(*, backfill: bool = True) -> dict[str, int]:
    """Idempotent bootstrap. Safe to call on every cold start."""
    store = get_store()
    already = await store.count(CONTROLS)

    result = {
        "controls": await seed_controls(),
        "memories": await seed_memories(),
        "agents": await registry.publish_fleet(),
        "backfilled": 0,
    }

    if backfill and already == 0:
        result["backfilled"] = await backfill_history(weeks=settings.audit_window_weeks)

    run_id = "run-2026-q3"
    if await store.get(RUNS, run_id) is None:
        await store.put(
            RUNS,
            RunSummary(
                run_id=run_id,
                started_at=now() - timedelta(weeks=settings.audit_window_weeks) + timedelta(days=4),
                budget_usd=settings.run_budget_usd,
                cost_usd=4.19,
            ),
        )

    from app.core.store import recompute_summary

    await recompute_summary(run_id)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    print(asyncio.run(seed_all()))
