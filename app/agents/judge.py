"""Control Judge — the judgment layer.

This is the agent that makes ATLAS more than a scraper. Given a control's
criterion text and the artifacts collected for it, the Judge rules
SATISFIED / INSUFFICIENT / NEEDS_HUMAN with cited evidence and explicit
reasoning.

Two design decisions matter:

* It recalls Memory Bank beliefs BEFORE ruling. A verdict that ignores
  "Priya rejects screenshot evidence for CC6.1" is a verdict that will be
  overturned, and an overturned verdict costs a human touch — which is
  exactly the metric we optimise against.

* It has no collection scopes. It cannot go get more evidence to make its
  own life easier; it must rule on what exists or escalate. Separation of
  duties, enforced by IAM rather than by prompt.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agents.base import ModelUnavailable, build_agent, invoke, model_available, parse_json
from app.core import identity
from app.core.events import emit
from app.core.memory import memory_bank
from app.core.models import Control, Evidence, Ruling, Verdict
from app.core.store import EVIDENCE, get_store
from app.core.telemetry import span

log = logging.getLogger("atlas.judge")


class JudgeOutput(BaseModel):
    """Structured output contract. Gemini is constrained to this shape."""

    verdict: str = Field(description="One of SATISFIED, INSUFFICIENT, NEEDS_HUMAN")
    confidence: float = Field(description="0.0-1.0 confidence in the verdict")
    reasoning: str = Field(description="Two to four sentences citing specific facts from the evidence")
    cited_evidence: list[str] = Field(default_factory=list, description="Artifact names relied upon")
    blocking_question: str = Field(
        default="", description="If NEEDS_HUMAN, the single question a human must answer"
    )


_INSTRUCTION = """You are the Control Judge in a SOC 2 Type II audit. You decide whether the
collected evidence satisfies a control. You are rigorous, sceptical, and brief.

Rules:
1. Rule SATISFIED only if the evidence directly demonstrates the criterion is met
   for the whole audit period. Partial coverage is INSUFFICIENT.
2. Rule NEEDS_HUMAN when the evidence is complete but the decision requires a
   policy judgment a human owns (risk acceptance, precedent, interpretation).
3. Rule INSUFFICIENT when evidence is missing, stale, or does not address the criterion.
4. Cite artifacts by exact filename. Never invent an artifact.
5. Honour the organisational memory below — it records what this company's
   compliance lead and external auditor have previously required. Contradicting
   it without cause wastes a human's time.

## Organisational memory
{memories}

## Control
{control_id} — {control_name}
Criterion: {control_text}
Freshness SLA: {freshness} days

## Evidence on file ({count} artifacts)
{evidence}

Return JSON only:
{{"verdict": "...", "confidence": 0.0, "reasoning": "...", "cited_evidence": ["..."], "blocking_question": ""}}
"""


def _deterministic_ruling(
    control: Control,
    evidence: list[Evidence],
    *,
    trusted_policy_judgment: bool = False,
) -> Ruling:
    """Fallback reasoner used when Gemini is unreachable.

    Deliberately conservative: it will never award SATISFIED on thin evidence,
    because a false green is the one failure mode an audit tool cannot have.
    ``trusted_policy_judgment`` is an internal orchestration signal. It is never
    inferred from untrusted artifact text.
    """
    names = [e.name for e in evidence]
    if not evidence:
        return Ruling(
            verdict=Verdict.INSUFFICIENT,
            confidence=0.9,
            reasoning="No evidence has been collected for this control.",
            model="deterministic-fallback",
        )

    stale = [e for e in evidence if e.is_stale]
    if stale:
        return Ruling(
            verdict=Verdict.INSUFFICIENT,
            confidence=0.85,
            reasoning=f"{len(stale)} artifact(s) exceed the {control.freshness_days}-day freshness SLA.",
            cited_evidence=[e.name for e in stale],
            model="deterministic-fallback",
        )

    if len(evidence) < control.evidence_required:
        return Ruling(
            verdict=Verdict.INSUFFICIENT,
            confidence=0.8,
            reasoning=(
                f"{len(evidence)} of {control.evidence_required} required artifacts on file."
            ),
            cited_evidence=names,
            model="deterministic-fallback",
        )

    # Surface the known judgment calls encoded in the mock data.
    joined = " ".join(e.summary.lower() for e in evidence)
    if trusted_policy_judgment:
        return Ruling(
            verdict=Verdict.NEEDS_HUMAN,
            confidence=0.71,
            reasoning=(
                "Evidence is complete, but the artifact identifies a policy judgment "
                "that requires accountable human approval."
            ),
            cited_evidence=names,
            blocking_question="What policy decision should the accountable owner approve?",
            model="deterministic-fallback",
        )
    if "break-glass" in joined or "not reviewed" in joined:
        return Ruling(
            verdict=Verdict.NEEDS_HUMAN,
            confidence=0.71,
            reasoning=(
                "Evidence is complete but shows accounts provisioned outside the standard "
                "path. Whether this is acceptable is a policy judgment, not a factual one."
            ),
            cited_evidence=names,
            blocking_question=(
                "Is break-glass provisioning acceptable for contractors if logged and "
                "reviewed within 24 hours?"
            ),
            model="deterministic-fallback",
        )
    if "no alert coverage" in joined or "never been test-fired" in joined or "expired" in joined:
        return Ruling(
            verdict=Verdict.INSUFFICIENT,
            confidence=0.82,
            reasoning="Evidence identifies an uncovered service or a lapsed agreement within the audit period.",
            cited_evidence=names,
            model="deterministic-fallback",
        )

    return Ruling(
        verdict=Verdict.SATISFIED,
        confidence=0.86,
        reasoning=(
            f"{len(evidence)} artifacts on file, all within the {control.freshness_days}-day "
            "SLA, collectively addressing the criterion."
        ),
        cited_evidence=names,
        model="deterministic-fallback",
    )


async def rule(control: Control, run_id: str, trace_id: str) -> Ruling:
    """Produce a ruling for one control."""
    store = get_store()
    all_evidence: list[Evidence] = await store.list(EVIDENCE, limit=5000)
    evidence = [e for e in all_evidence if e.id in set(control.evidence_ids) and not e.superseded_by]

    with identity.assume("judge"):
        with span("memory_bank.recall", agent="judge", trace_id=trace_id, control=control.id) as sp:
            memories = await memory_bank.recall(
                f"{control.id} {control.name} {control.text}", subject=control.id
            )
            sp.attributes["memories"] = len(memories)

        ruling: Ruling
        if model_available() and evidence:
            try:
                with span("gemini.rule", agent="judge", trace_id=trace_id,
                          model=control and "gemini-3.5-flash") as sp:
                    agent = build_agent(
                        "control_judge",
                        _INSTRUCTION.format(
                            memories=memory_bank.as_prompt_block(memories),
                            control_id=control.id,
                            control_name=control.name,
                            control_text=control.text or control.name,
                            freshness=control.freshness_days,
                            count=len(evidence),
                            evidence="\n".join(
                                f"- {e.name} ({e.kind}, from {e.source_system}, "
                                f"{e.age_days}d old): {e.summary}"
                                for e in evidence
                            ),
                        ),
                        model=None,
                        description="Rules whether evidence satisfies a SOC 2 control",
                    )
                    raw = await invoke(agent, f"Rule on {control.id}.", session_id=f"judge-{control.id}")
                    data = parse_json(raw)
                    sp.attributes["verdict"] = data.get("verdict", "?")
                ruling = Ruling(
                    verdict=Verdict(data["verdict"]),
                    confidence=float(data.get("confidence", 0.0)),
                    reasoning=data.get("reasoning", ""),
                    cited_evidence=data.get("cited_evidence", []),
                    blocking_question=data.get("blocking_question") or None,
                    model="gemini-3.5-flash",
                )
            except (ModelUnavailable, ValueError, KeyError, Exception) as exc:
                log.info("judge fell back to deterministic reasoning (%s)", type(exc).__name__)
                ruling = _deterministic_ruling(control, evidence)
        else:
            ruling = _deterministic_ruling(control, evidence)

        ruling.trace_id = trace_id
        ruling.memories_used = [m.id for m in memories]

        await emit(
            "judge",
            "ruled",
            f"{control.id} → {ruling.verdict.value}"
            + (f" · {ruling.reasoning[:70]}" if ruling.reasoning else ""),
            control_id=control.id,
            severity="warn" if ruling.verdict is not Verdict.SATISFIED else "info",
            trace_id=trace_id,
            verdict=ruling.verdict.value,
            confidence=ruling.confidence,
        )

    return ruling
