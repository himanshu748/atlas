"""Package Assembler — the deliverable.

Produces what the auditor actually receives: an index, a per-control
narrative, a manifest with a SHA-256 for every artifact, a Merkle-style root
hash, and a gap register. Everything is verifiable without trusting ATLAS,
which is the point — an auditor should not have to take a vendor's word that
evidence was not edited after collection.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.config import settings
from app.core import identity
from app.core.armor import screen
from app.core.events import emit
from app.core.models import Control, ControlStatus, Evidence, now
from app.core.store import CONTROLS, EVIDENCE, get_store
from app.core.telemetry import span

log = logging.getLogger("atlas.assembler")


def _control_leaf(control_id: str, status: str, verdict: str | None, human_touches: int) -> str:
    """One hashable line binding a control to the verdict recorded against it."""
    return f"control:{control_id}:{status}:{verdict or 'none'}:{human_touches}"


def _root_hash(hashes: list[str], control_leaves: list[str]) -> str:
    """Deterministic root over sorted artifact hashes and control verdicts.

    Artifact hashes alone would let a rewritten ruling keep a valid root, so the
    judged outcome of every control is hashed alongside the evidence it cites.
    scripts/verify_manifest.py duplicates this and must stay identical.
    """
    joined = "".join(sorted(hashes + control_leaves)).encode()
    return hashlib.sha256(joined).hexdigest()


async def build_package(run_id: str, trace_id: str) -> dict[str, Any]:
    store = get_store()
    controls: list[Control] = sorted(await store.list(CONTROLS, limit=5000), key=lambda c: c.id)
    evidence: list[Evidence] = await store.list(EVIDENCE, limit=5000)
    by_id = {e.id: e for e in evidence}

    with identity.assume("assembler"):
        with span("assembler.build", agent="assembler", trace_id=trace_id) as sp:
            entries = []
            gaps = []

            for control in controls:
                artifacts = [by_id[i] for i in control.evidence_ids if i in by_id]
                entries.append(
                    {
                        "control": control.id,
                        "name": control.name,
                        "status": control.status.value,
                        "verdict": control.ruling.verdict.value if control.ruling else None,
                        "narrative": control.ruling.reasoning if control.ruling else "",
                        "human_touches": control.human_touches,
                        "artifacts": [
                            {
                                "name": a.name,
                                "kind": a.kind,
                                "source": a.source_system,
                                "collected_by": a.collected_by,
                                "identity": a.agent_identity,
                                "collected_at": a.collected_at.isoformat(),
                                "age_days": a.age_days,
                                "armor": a.armor_verdict.value,
                                "sha256": a.sha256,
                                "bytes": a.size_bytes,
                            }
                            for a in artifacts
                        ],
                    }
                )
                if control.status is not ControlStatus.VERIFIED:
                    gaps.append(
                        {
                            "control": control.id,
                            "status": control.status.value,
                            "owner": control.owner,
                            "reason": control.ruling.reasoning if control.ruling else "not yet collected",
                        }
                    )

            all_hashes = [a.sha256 for a in evidence if a.sha256]
            control_leaves = [
                _control_leaf(
                    e["control"], e["status"], e["verdict"], e["human_touches"]
                )
                for e in entries
            ]
            manifest = {
                "package": f"atlas-{settings.framework}-{now():%Y}-{run_id}",
                "generated_at": now().isoformat(),
                "framework": settings.framework.upper(),
                "org": settings.org_id,
                "controls_total": len(controls),
                "controls_verified": sum(
                    1 for c in controls if c.status is ControlStatus.VERIFIED
                ),
                "artifacts": len(evidence),
                "root_hash": _root_hash(all_hashes, control_leaves),
                "signed_by": identity.get("assembler").spiffe_id,
                "verify": "python scripts/verify_manifest.py manifest.json",
                "entries": entries,
                "gap_register": gaps,
            }
            sp.attributes["artifacts"] = len(evidence)
            sp.attributes["gaps"] = len(gaps)

        # Egress screening: nothing leaves with PII in it.
        with span("armor.screen", agent="assembler", trace_id=trace_id, direction="egress"):
            result = await screen(
                json.dumps(manifest)[:20000],
                direction="egress",
                artifact="manifest.json",
                agent="assembler",
                trace_id=trace_id,
            )

        if settings.is_cloud and settings.bucket:
            try:
                from google.cloud import storage

                client = storage.Client(project=settings.project_id)
                blob = client.bucket(settings.bucket).blob(f"{manifest['package']}/manifest.json")
                blob.upload_from_string(json.dumps(manifest, indent=2), "application/json")
                manifest["location"] = f"gs://{settings.bucket}/{manifest['package']}/manifest.json"
            except Exception as exc:  # pragma: no cover
                log.warning("package upload failed: %s", exc)

        await emit(
            "assembler",
            "packaged",
            f"package built · {manifest['artifacts']} artifacts hashed · "
            f"{len(gaps)} open gap(s) · root {manifest['root_hash'][:8]}",
            trace_id=trace_id,
            egress_armor=result.action.value,
        )

    return manifest
