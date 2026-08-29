"""Memory Bank — what the fleet knows about this org.

Persistence is not memory. A Firestore row that nobody retrieves at decision
time is just storage. These helpers exist so the Control Judge *fetches
relevant beliefs before ruling* and *writes new beliefs after a human
corrects it* — which is what makes next year's audit start at 80% instead
of zero.

Vertex mode can connect to managed services; AI Studio and local modes use
the ledger with keyword scoring so behaviour is identical offline.
"""
from __future__ import annotations

import logging
import re

from app.config import settings
from app.core.models import Memory, now
from app.core.store import MEMORIES, get_store

log = logging.getLogger("atlas.memory")

_STOP = {
    "the", "a", "an", "is", "are", "for", "of", "to", "and", "or", "in", "on",
    "with", "that", "this", "it", "as", "be", "by", "from", "must", "should",
}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9.]+", text.lower()) if w not in _STOP and len(w) > 2}


class MemoryBank:
    """Retrieve-before-decide, reinforce-after-correct."""

    def __init__(self) -> None:
        self._cloud = None
        if settings.use_vertex_ai:
            try:
                from google import genai

                self._cloud = genai.Client(
                    vertexai=True, project=settings.project_id, location=settings.location
                )
                log.info("memory bank: vertex profile=%s", settings.memory_profile)
            except Exception as exc:  # pragma: no cover
                log.warning("memory bank unavailable (%s); using ledger", exc)

    async def recall(self, query: str, *, subject: str = "", limit: int = 4) -> list[Memory]:
        """Fetch the beliefs most relevant to a decision about to be made."""
        store = get_store()
        all_memories: list[Memory] = await store.list(MEMORIES, limit=500)
        if not all_memories:
            return []

        q = _tokens(f"{query} {subject}")
        scored: list[tuple[float, Memory]] = []
        for m in all_memories:
            overlap = len(q & _tokens(m.text))
            if subject and m.subject and subject.lower() == m.subject.lower():
                overlap += 4  # exact-subject memories dominate
            if overlap:
                scored.append((overlap * m.confidence, m))

        scored.sort(key=lambda p: p[0], reverse=True)
        picked = [m for _, m in scored[:limit]]
        for m in picked:
            m.last_used = now()
            await store.put(MEMORIES, m)
        return picked

    async def remember(
        self,
        text: str,
        *,
        subject: str = "",
        scope: str = "org",
        source_run: str = "",
        confidence: float = 0.7,
    ) -> Memory:
        """Write a belief, reinforcing instead of duplicating near-matches."""
        store = get_store()
        existing: list[Memory] = await store.list(MEMORIES, limit=500)
        new_tokens = _tokens(text)

        for m in existing:
            overlap = len(new_tokens & _tokens(m.text))
            denom = max(1, len(new_tokens | _tokens(m.text)))
            if overlap / denom > 0.6:  # jaccard — same belief, restated
                m.reinforced += 1
                m.confidence = min(1.0, m.confidence + 0.06)
                await store.put(MEMORIES, m)
                return m

        memory = Memory(
            text=text,
            subject=subject,
            scope=scope,
            source_run=source_run,
            confidence=confidence,
        )
        await store.put(MEMORIES, memory)
        log.info("memory written: %s", text[:80])
        return memory

    @staticmethod
    def as_prompt_block(memories: list[Memory]) -> str:
        """Render recalled beliefs for injection into an agent's instruction."""
        if not memories:
            return "No prior organisational context for this control."
        lines = [
            f"- {m.text} (confidence {m.confidence:.2f}, reinforced {m.reinforced}×)"
            for m in memories
        ]
        return "\n".join(lines)


memory_bank = MemoryBank()
