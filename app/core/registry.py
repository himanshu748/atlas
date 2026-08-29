"""Agent Registry — discovery and versioning.

The orchestrator never hardcodes a sub-agent endpoint. It asks the registry,
which is what lets Legal subscribe the vendor hunter for GDPR work without
touching Security's deployment, and what lets us roll hunter/iam from 1.9.0
to 2.0.0 behind a version pin.

Cloud mode resolves through the Gemini Enterprise Agent Registry; local mode
serves the same cards from the ledger so the console and the orchestrator
behave identically offline.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.core.identity import IDENTITIES
from app.core.models import AgentCard
from app.core.store import AGENTS, get_store

log = logging.getLogger("atlas.registry")

# The published fleet. Version numbers are real: bump them when behaviour changes.
FLEET: list[AgentCard] = [
    AgentCard(
        name="orchestrator",
        version="2.4.1",
        description="Plans the audit window, assigns controls to domain agents, arbitrates conflicts, enforces the budget governor.",
        spiffe_id=IDENTITIES["orchestrator"].spiffe_id,
        scopes=sorted(IDENTITIES["orchestrator"].scopes),
        departments=["Security", "IT", "Legal"],
    ),
    AgentCard(
        name="hunter/iam",
        version="1.9.0",
        description="Access reviews, MFA enforcement, privileged account inventory. Reads GCP IAM bindings and Workspace admin state.",
        spiffe_id=IDENTITIES["hunter/iam"].spiffe_id,
        scopes=sorted(IDENTITIES["hunter/iam"].scopes),
        departments=["Security", "IT"],
    ),
    AgentCard(
        name="hunter/sdlc",
        version="1.7.2",
        description="Branch protection, PR review enforcement, CI gates, secret-scanning results.",
        spiffe_id=IDENTITIES["hunter/sdlc"].spiffe_id,
        scopes=sorted(IDENTITIES["hunter/sdlc"].scopes),
        departments=["Security", "IT"],
    ),
    AgentCard(
        name="hunter/infra",
        version="1.8.1",
        description="Encryption at rest and in transit, backup configuration, network policy, log retention.",
        spiffe_id=IDENTITIES["hunter/infra"].spiffe_id,
        scopes=sorted(IDENTITIES["hunter/infra"].scopes),
        departments=["Security", "IT"],
    ),
    AgentCard(
        name="hunter/hr",
        version="1.4.0",
        description="Onboarding and offboarding timeliness, background checks, security-training completion. PII-restricted.",
        spiffe_id=IDENTITIES["hunter/hr"].spiffe_id,
        scopes=sorted(IDENTITIES["hunter/hr"].scopes),
        departments=["Security"],
    ),
    AgentCard(
        name="hunter/vendor",
        version="1.3.3",
        description="Third-party SOC 2 reports and DPAs. Highest injection risk, so it runs the strictest Model Armor template.",
        spiffe_id=IDENTITIES["hunter/vendor"].spiffe_id,
        scopes=sorted(IDENTITIES["hunter/vendor"].scopes),
        departments=["Security", "Legal"],
    ),
    AgentCard(
        name="judge",
        version="2.1.0",
        description="Rules whether candidate evidence satisfies a control. Never collects — only rules. Separation of duties.",
        spiffe_id=IDENTITIES["judge"].spiffe_id,
        scopes=sorted(IDENTITIES["judge"].scopes),
        departments=["Security", "IT", "Legal"],
    ),
    AgentCard(
        name="chaser",
        version="1.5.4",
        description="Owns human interaction: minimal-context nudges, escalation ladder, dedupe so an owner is never pinged twice.",
        spiffe_id=IDENTITIES["chaser"].spiffe_id,
        scopes=sorted(IDENTITIES["chaser"].scopes),
        departments=["Security"],
    ),
    AgentCard(
        name="sentinel",
        version="1.2.0",
        description="Weekly sweeps. Recomputes freshness SLAs, detects regressions, reopens work autonomously.",
        spiffe_id=IDENTITIES["sentinel"].spiffe_id,
        scopes=sorted(IDENTITIES["sentinel"].scopes),
        departments=["Security"],
    ),
    AgentCard(
        name="assembler",
        version="0.9.2",
        description="Builds the auditor deliverable: index, per-control narratives, SHA-256 manifest, gap register.",
        spiffe_id=IDENTITIES["assembler"].spiffe_id,
        scopes=sorted(IDENTITIES["assembler"].scopes),
        departments=["Security"],
    ),
    AgentCard(
        name="redactor",
        version="0.3.1",
        framework="GenAI",
        description="Self-hosted Gemma 3. Strips PII inside the trust boundary before anything leaves. Data sovereignty by architecture.",
        spiffe_id=IDENTITIES["redactor"].spiffe_id,
        scopes=[],
        departments=["Security"],
    ),
]


async def publish_fleet() -> int:
    """Register every agent at startup. Idempotent."""
    store = get_store()
    for card in FLEET:
        existing = await store.get(AGENTS, card.name)
        if existing:
            card.invocations = existing.invocations
        await store.put(AGENTS, card)
    log.info("registry: published %d agents", len(FLEET))
    return len(FLEET)


async def resolve(name: str) -> AgentCard | None:
    """What the orchestrator calls instead of hardcoding a URL."""
    card = await get_store().get(AGENTS, name)
    if card is None:
        log.warning("registry: no agent named %s", name)
    return card


async def record_invocation(name: str) -> None:
    store = get_store()
    card = await store.get(AGENTS, name)
    if card:
        card.invocations += 1
        await store.put(AGENTS, card)


async def search(capability: str) -> list[AgentCard]:
    """Keyword discovery — how another department finds a useful agent."""
    cards: list[AgentCard] = await get_store().list(AGENTS, limit=200)
    needle = capability.lower()
    return [
        c
        for c in cards
        if needle in c.name.lower()
        or needle in c.description.lower()
        or any(needle in s.lower() for s in c.scopes)
    ]


async def resolve_remote(name: str):  # pragma: no cover - requires GCP
    """Cloud path: fetch a live A2A handle through the Agent Registry + Gateway.

    Kept separate from `resolve` so local mode never imports GCP libraries.
    """
    if not settings.use_vertex_ai:
        return None
    try:
        from google.adk.tools.agent_tool import AgentTool  # noqa: F401
        from vertexai import agent_registry  # type: ignore

        client = agent_registry.AgentRegistry(
            project=settings.project_id, location=settings.location
        )
        return client.get_remote_a2a_agent(name)
    except Exception as exc:
        log.warning("remote resolve failed for %s (%s); using in-process agent", name, exc)
        return None
