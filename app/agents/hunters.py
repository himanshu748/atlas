"""Evidence Hunters — five domain-scoped collectors.

Each hunter runs under its own SPIFFE identity, so the IAM hunter literally
cannot call the HR connector. Untrusted artifacts (anything authored outside
the company) are screened by Model Armor *before* their text is allowed near
a model that holds tool credentials.

A hunter never decides whether a control is satisfied. It collects, hashes,
files, and stops. Judgment belongs to the Control Judge — separation of
duties, copied from how real audit teams work.
"""
from __future__ import annotations

import logging

from app.agents.base import ModelUnavailable, build_agent, invoke, model_available
from app.connectors import AGENT_FOR_DOMAIN, COLLECTORS
from app.core import identity
from app.core.armor import screen
from app.core.events import emit
from app.core.models import ArmorAction, Control, Domain, Evidence
from app.core.store import CONTROLS, EVIDENCE, get_store
from app.core.telemetry import span

log = logging.getLogger("atlas.hunter")

_INSTRUCTION = """You are an evidence hunter for a SOC 2 audit, scoped to the {domain} domain.

You receive raw artifacts pulled from company systems. For each artifact,
write one precise sentence describing what it PROVES or FAILS TO PROVE about
the control below. State facts and numbers found in the artifact. Never
speculate, never soften a gap, and never conclude whether the control passes —
that is the Control Judge's job.

Control: {control_id} — {control_name}
Criterion: {control_text}

Respond with one line per artifact, in the form:
<artifact-name>: <what it proves or fails to prove>
"""


async def hunt(control: Control, run_id: str, trace_id: str) -> list[Evidence]:
    """Collect, screen, hash and file evidence for one control."""
    agent_name = AGENT_FOR_DOMAIN[control.domain]
    collector = COLLECTORS[control.domain]
    store = get_store()
    filed: list[Evidence] = []

    with identity.assume(agent_name):
        with span(f"{agent_name}.collect", agent=agent_name, trace_id=trace_id,
                  control=control.id) as sp:
            artifacts = await collector(control.id)
            sp.attributes["artifacts"] = len(artifacts)

        # ---- screen anything authored outside the trust boundary ----
        safe = []
        for art in artifacts:
            if art["trusted"]:
                safe.append(art)
                continue
            with span("armor.screen", agent=agent_name, trace_id=trace_id,
                      artifact=art["name"], direction="ingress"):
                result = await screen(
                    art["text"],
                    direction="ingress",
                    artifact=art["name"],
                    agent=agent_name,
                    trace_id=trace_id,
                )
            if not result.allowed:
                # Quarantined. The ledger is never touched by a poisoned artifact.
                await emit(
                    agent_name,
                    "quarantined",
                    f"quarantined {art['name']} — {result.policy}",
                    control_id=control.id,
                    severity="alert",
                    trace_id=trace_id,
                )
                continue
            if result.action is ArmorAction.REDACTED:
                art["text"] = result.text
            safe.append(art)

        # ---- let the model characterise what each artifact proves ----
        summaries: dict[str, str] = {}
        if safe and model_available():
            try:
                with span("gemini.summarise", agent=agent_name, trace_id=trace_id,
                          model="gemini-3.5-flash") as sp:
                    agent = build_agent(
                        f"hunter_{control.domain.value}",
                        _INSTRUCTION.format(
                            domain=control.domain.value,
                            control_id=control.id,
                            control_name=control.name,
                            control_text=control.text or control.name,
                        ),
                        description=f"Evidence hunter for the {control.domain.value} domain",
                    )
                    payload = "\n\n".join(
                        f"### {a['name']} ({a['kind']}, from {a['source_system']})\n{a['text'][:4000]}"
                        for a in safe
                    )
                    out = await invoke(agent, payload, session_id=f"hunt-{control.id}")
                    sp.attributes["chars"] = len(out)
                for line in out.splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        summaries[k.strip().lstrip("-* ")] = v.strip()
            except (ModelUnavailable, Exception) as exc:
                log.info("hunter summarisation skipped (%s)", type(exc).__name__)

        # ---- file each artifact with full provenance ----
        for art in safe:
            ev = Evidence(
                control_id=control.id,
                name=art["name"],
                kind=art["kind"],
                source_system=art["source_system"],
                collected_by=agent_name,
                agent_identity=identity.get(agent_name).spiffe_id,
                freshness_days=control.freshness_days,
                sha256=Evidence.hash_payload(art["text"]),
                size_bytes=art["size_bytes"],
                summary=summaries.get(art["name"]) or art["summary"],
                payload_ref=f"local://evidence/{control.id}/{art['name']}",
            )
            await store.put(EVIDENCE, ev)
            filed.append(ev)

        if filed:
            control.evidence_ids = sorted({*control.evidence_ids, *[e.id for e in filed]})
            control.updated_by = agent_name
            await store.put(CONTROLS, control)
            await emit(
                agent_name,
                "collected",
                f"filed {len(filed)} artifact(s) for {control.id}",
                control_id=control.id,
                trace_id=trace_id,
            )

    return filed


def hunter_domains() -> list[Domain]:
    return list(COLLECTORS.keys())
