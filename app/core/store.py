"""Durable state.

Two backends behind one interface:
  * FirestoreStore  — production. Collections are flat and query-friendly.
  * MemoryStore     — local dev + judges running the container with no creds.

The repository interface is intentionally narrow (get/put/list/patch) so the
agents never learn Firestore semantics. Swapping to Cloud SQL would touch
one file.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Iterable, TypeVar
from urllib.parse import quote

from app.config import settings
from app.core.models import (
    AgentCard,
    ArmorVerdict,
    Control,
    Evidence,
    FleetEvent,
    Handoff,
    Memory,
    RunSummary,
    Task,
    TaskState,
    now,
)

log = logging.getLogger("atlas.store")

T = TypeVar("T")

CONTROLS = "controls"
EVIDENCE = "evidence"
HANDOFFS = "handoffs"
ARMOR = "armor_verdicts"
MEMORIES = "memories"
TASKS = "tasks"
EVENTS = "events"
AGENTS = "agent_cards"
RUNS = "runs"

_MODEL_FOR = {
    CONTROLS: Control,
    EVIDENCE: Evidence,
    HANDOFFS: Handoff,
    ARMOR: ArmorVerdict,
    MEMORIES: Memory,
    TASKS: Task,
    EVENTS: FleetEvent,
    AGENTS: AgentCard,
    RUNS: RunSummary,
}

_KEY_FOR = {
    CONTROLS: "id",
    EVIDENCE: "id",
    HANDOFFS: "id",
    ARMOR: "id",
    MEMORIES: "id",
    TASKS: "key",
    EVENTS: "id",
    AGENTS: "name",
    RUNS: "run_id",
}


def _firestore_doc_key(key: object) -> str:
    """Encode logical keys so names such as ``hunter/iam`` stay one document ID."""
    return quote(str(key), safe="")


class MemoryStore:
    """In-process store. Thread-safe enough for a single Cloud Run instance."""

    def __init__(self) -> None:
        self._db: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def put(self, coll: str, obj: Any) -> Any:
        async with self._lock:
            key = getattr(obj, _KEY_FOR[coll])
            self._db[coll][key] = obj.model_dump(mode="json")
        return obj

    async def get(self, coll: str, key: str) -> Any | None:
        raw = self._db[coll].get(key)
        return _MODEL_FOR[coll](**raw) if raw else None

    async def list(self, coll: str, limit: int = 1000) -> list[Any]:
        rows = list(self._db[coll].values())[:limit]
        return [_MODEL_FOR[coll](**r) for r in rows]

    async def patch(self, coll: str, key: str, **fields: Any) -> Any | None:
        async with self._lock:
            raw = self._db[coll].get(key)
            if raw is None:
                return None
            obj = _MODEL_FOR[coll](**raw)
            for k, v in fields.items():
                setattr(obj, k, v)
            self._db[coll][key] = obj.model_dump(mode="json")
        return obj

    async def delete(self, coll: str, key: str) -> None:
        async with self._lock:
            self._db[coll].pop(key, None)

    async def count(self, coll: str) -> int:
        return len(self._db[coll])


class FirestoreStore:
    """Cloud backend. Same interface; async client so we never block the loop."""

    def __init__(self) -> None:
        from google.cloud import firestore  # imported lazily — local mode has no dep

        self._client = firestore.AsyncClient(
            project=settings.project_id, database=settings.firestore_db
        )

    def _col(self, coll: str):
        return self._client.collection(f"atlas_{coll}")

    async def put(self, coll: str, obj: Any) -> Any:
        key = getattr(obj, _KEY_FOR[coll])
        await self._col(coll).document(_firestore_doc_key(key)).set(obj.model_dump(mode="json"))
        return obj

    async def get(self, coll: str, key: str) -> Any | None:
        snap = await self._col(coll).document(_firestore_doc_key(key)).get()
        return _MODEL_FOR[coll](**snap.to_dict()) if snap.exists else None

    async def list(self, coll: str, limit: int = 1000) -> list[Any]:
        out = []
        async for snap in self._col(coll).limit(limit).stream():
            out.append(_MODEL_FOR[coll](**snap.to_dict()))
        return out

    async def patch(self, coll: str, key: str, **fields: Any) -> Any | None:
        obj = await self.get(coll, key)
        if obj is None:
            return None
        for k, v in fields.items():
            setattr(obj, k, v)
        return await self.put(coll, obj)

    async def delete(self, coll: str, key: str) -> None:
        await self._col(coll).document(_firestore_doc_key(key)).delete()

    async def count(self, coll: str) -> int:
        return len(await self.list(coll, limit=5000))


Store = MemoryStore | FirestoreStore
_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        if settings.is_cloud:
            try:
                _store = FirestoreStore()
                log.info("store: firestore project=%s", settings.project_id)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("firestore unavailable (%s); falling back to memory", exc)
                _store = MemoryStore()
        else:
            _store = MemoryStore()
            log.info("store: in-memory (ATLAS_MODE=local)")
    return _store


# ------------------------------------------------------------------ helpers
async def claim_task(run_id: str, control_id: str, step: str, agent: str) -> Task | None:
    """Idempotency gate.

    Returns a Task if this unit of work has NOT already been done, else None.
    Directly addresses the resumable-agent double-execution trap: a redelivered
    Pub/Sub message for an already-completed step is a no-op.
    """
    store = get_store()
    key = Task.make_key(run_id, control_id, step)
    existing = await store.get(TASKS, key)
    if existing and existing.state in (TaskState.DONE, TaskState.IN_PROGRESS):
        return None
    task = existing or Task(key=key, run_id=run_id, control_id=control_id, step=step, agent=agent)
    task.state = TaskState.IN_PROGRESS
    task.attempts += 1
    task.updated_at = now()
    await store.put(TASKS, task)
    return task


async def complete_task(task: Task, error: str = "") -> None:
    task.state = TaskState.FAILED if error else TaskState.DONE
    task.error = error
    task.updated_at = now()
    await get_store().put(TASKS, task)


async def recompute_summary(run_id: str) -> RunSummary:
    """Derive fleet posture from the ledger. Single source of truth for the UI."""
    store = get_store()
    controls: Iterable[Control] = await store.list(CONTROLS, limit=5000)
    controls = list(controls)
    handoffs: list[Handoff] = await store.list(HANDOFFS, limit=5000)

    summary = await store.get(RUNS, run_id)
    if summary is None:
        summary = RunSummary(run_id=run_id, started_at=now(), budget_usd=settings.run_budget_usd)

    summary.controls_total = len(controls)
    summary.controls_verified = sum(1 for c in controls if c.status.value == "verified")
    summary.controls_autonomous = sum(1 for c in controls if c.closed_autonomously)
    summary.handoffs_open = sum(1 for h in handoffs if h.is_open)
    summary.events_emitted = await store.count(EVENTS)
    await store.put(RUNS, summary)
    return summary
