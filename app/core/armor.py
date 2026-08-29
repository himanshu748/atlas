"""Model Armor — the trust boundary.

Every byte that enters an agent from a third-party system, and every byte
that leaves toward one, passes through here. This is not decoration: the
Vendor hunter ingests PDFs written by other companies and feeds them to a
model that holds tool credentials. That is textbook indirect prompt
injection, and it is the single most likely way an agentic compliance
system gets subverted.

In cloud mode this calls the Model Armor API. In local mode it runs a
deterministic detector so the behaviour — and the demo — is identical
without credentials.
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from app.config import settings
from app.core.models import ArmorAction, ArmorVerdict
from app.core.store import ARMOR, get_store

log = logging.getLogger("atlas.armor")

# Patterns that indicate an attempt to retarget the model's instructions.
# Ordered most-specific first so `matched_policy` is informative.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(all\s+)?(prior|previous|above)\s+instructions", "prompt-injection.override"),
    (r"disregard\s+(your|all|the)\s+(instructions|rules|system)", "prompt-injection.override"),
    (r"system\s*(note|prompt|message)\s*(to|for)\s*(the\s*)?(ai|assistant|reviewer|model)", "prompt-injection.impersonate-system"),
    (r"mark\s+(all|every)\s+controls?\s+.{0,24}\bsatisfied\b", "prompt-injection.verdict-tampering"),
    (r"do\s+not\s+(flag|report|escalate)\s+(any\s+)?(exceptions?|issues?|findings?)", "prompt-injection.suppress-findings"),
    (r"you\s+are\s+now\s+a\s+", "prompt-injection.role-hijack"),
    (r"respond\s+only\s+with\s+(approval|yes|satisfied)", "prompt-injection.forced-output"),
    (r"<\|im_start\|>|<\|system\|>|\[\[SYSTEM\]\]", "prompt-injection.control-tokens"),
]

# PII we redact on egress. Deliberately conservative — false positives are
# cheap, a leaked SSN in an auditor package is not.
_PII_PATTERNS: list[tuple[str, str]] = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "pii.ssn"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b", "pii.email"),
    (r"\b(?:\d[ -]*?){13,16}\b", "pii.card"),
    (r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", "pii.aws-key"),
    (r"\bghp_[A-Za-z0-9]{36}\b", "pii.github-token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "pii.private-key"),
]


class ArmorResult:
    __slots__ = ("action", "policy", "confidence", "text", "excerpt", "backend")

    def __init__(
        self,
        action: ArmorAction,
        policy: str = "",
        confidence: float = 0.0,
        text: str = "",
        excerpt: str = "",
        backend: Literal[
            "model-armor",
            "model-armor+deterministic",
            "deterministic-fallback",
        ] = "deterministic-fallback",
    ) -> None:
        self.action = action
        self.policy = policy
        self.confidence = confidence
        self.text = text          # sanitised text safe to hand to a model
        self.excerpt = excerpt    # sanitised evidence for the UI
        self.backend = backend

    @property
    def allowed(self) -> bool:
        return self.action is not ArmorAction.BLOCKED


def _excerpt_around(text: str, match: re.Match, width: int = 120) -> str:
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def _screen_local(text: str, direction: str) -> ArmorResult:
    """Deterministic detector used in local mode and as a cloud-outage fallback."""
    if direction == "ingress":
        for pattern, policy in _INJECTION_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return ArmorResult(
                    ArmorAction.BLOCKED,
                    policy,
                    0.97,
                    text="",
                    excerpt=_excerpt_around(text, m),
                )

    redacted, hits = text, []
    for pattern, policy in _PII_PATTERNS:
        redacted, n = re.subn(pattern, lambda m: f"[REDACTED:{policy.split('.')[-1]}]", redacted)
        if n:
            hits.append(f"{policy}×{n}")
    if hits:
        return ArmorResult(ArmorAction.REDACTED, ",".join(hits), 0.88, text=redacted)
    return ArmorResult(ArmorAction.PASS, "", 0.0, text=text)


def _screen_after_managed_pass(text: str, direction: str) -> ArmorResult:
    """Apply the local guard after a clean managed verdict.

    Model Armor remains the primary managed boundary. The deterministic pass is
    deliberately additive so a known high-signal payload cannot reach an agent
    merely because one classifier returned a clean result.
    """
    result = _screen_local(text, direction)
    result.backend = "model-armor+deterministic"
    return result


def _screen_cloud(text: str, direction: str) -> ArmorResult:
    """Call the Model Armor API. Falls back to local on any failure."""
    try:
        from google.api_core.client_options import ClientOptions
        from google.cloud import modelarmor_v1

        client = modelarmor_v1.ModelArmorClient(
            client_options=ClientOptions(
                api_endpoint=f"modelarmor.{settings.location}.rep.googleapis.com"
            )
        )
        template = (
            settings.armor_template_ingress
            if direction == "ingress"
            else settings.armor_template_egress
        )
        name = (
            f"projects/{settings.project_id}/locations/{settings.location}"
            f"/templates/{template}"
        )
        request = {"name": name}
        if direction == "ingress":
            request["user_prompt_data"] = {"text": text}
            resp = client.sanitize_user_prompt(request=request)
        else:
            request["model_response_data"] = {"text": text}
            resp = client.sanitize_model_response(request=request)
        result = resp.sanitization_result
        verdict = str(getattr(result, "filter_match_state", ""))
        if "MATCH_FOUND" in verdict:
            findings = str(getattr(result, "filter_results", ""))[:200]
            return ArmorResult(
                ArmorAction.BLOCKED,
                "model-armor.match",
                0.95,
                "",
                findings,
                backend="model-armor",
            )
        return _screen_after_managed_pass(text, direction)
    except Exception as exc:
        log.warning("model armor call failed (%s); using local detector", exc)
        return _screen_local(text, direction)


async def screen(
    text: str,
    *,
    direction: Literal["ingress", "egress"],
    artifact: str,
    agent: str,
    trace_id: str = "",
) -> ArmorResult:
    """Screen a payload and record the verdict. Always record — even a pass.

    A clean verdict log is itself audit evidence: it proves every third-party
    byte was inspected, which is what an auditor actually asks for.
    """
    result = (
        _screen_cloud(text, direction)
        if settings.is_cloud and settings.use_managed_armor
        else _screen_local(text, direction)
    )

    template = (
        settings.armor_template_ingress if direction == "ingress" else settings.armor_template_egress
    )
    verdict = ArmorVerdict(
        direction=direction,
        artifact=artifact,
        agent=agent,
        template=template,
        action=result.action,
        matched_policy=result.policy,
        confidence=result.confidence,
        backend=result.backend,
        excerpt=result.excerpt[:600],
        trace_id=trace_id,
    )
    await get_store().put(ARMOR, verdict)

    if result.action is ArmorAction.BLOCKED:
        from app.core.events import emit

        await emit(
            "armor",
            "blocked",
            f"BLOCKED {artifact} · {result.policy}",
            severity="alert",
            trace_id=trace_id,
            artifact=artifact,
            policy=result.policy,
        )
    elif result.action is ArmorAction.REDACTED:
        from app.core.events import emit

        await emit(
            "armor",
            "redacted",
            f"screened {artifact} · {result.policy}",
            severity="warn",
            trace_id=trace_id,
        )
    return result
