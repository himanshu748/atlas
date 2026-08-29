"""Multimodal evidence.

Compliance evidence is genuinely multimodal — this is not a bolt-on. In a real
audit roughly half the artifacts are screenshots of admin consoles, third-party
SOC 2 reports run to a hundred-plus pages, and access-review walkthroughs are
recorded as video. Text-only ingestion would simply fail on most of the corpus.

Three capabilities live here:

1. `parse_visual_evidence` — send an image/PDF/video to gemini-3.5-flash and
   extract a *structured, checkable claim*. The source media is retained and
   pinned next to its interpretation in the UI, so a human can always verify
   what the model read. A model reading a screenshot is a witness, not an
   oracle.

2. `daily_briefing` — a 45-second spoken standup for the compliance lead.
   Gemini writes the script from live ledger state; Cloud Text-to-Speech
   renders it. Note that gemini-3.5-flash does not generate audio, so this is
   an explicit two-stage pipeline rather than a single call.

3. `redact_locally` — the Gemma 3 path. Runs inside the trust boundary so PII
   never crosses it, which is what makes the data-sovereignty story real
   rather than aspirational.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import (
    ModelUnavailable,
    build_genai_client,
    model_available,
    parse_json,
)
from app.config import settings
from app.core import identity
from app.core.events import emit
from app.core.models import Control, ControlStatus, now
from app.core.store import CONTROLS, HANDOFFS, get_store
from app.core.telemetry import span

log = logging.getLogger("atlas.multimodal")

MediaKind = Literal["image", "pdf", "video", "audio"]

_MIME = {
    "image": "image/png",
    "pdf": "application/pdf",
    "video": "video/mp4",
    "audio": "audio/mpeg",
}


class VisualClaim(BaseModel):
    """What a model says it saw. Deliberately narrow and checkable."""

    claim: str = Field(description="One sentence stating the configuration state observed")
    supports_control: bool = Field(description="Whether the observed state supports the control")
    observed_values: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    caveats: str = ""
    model: str = ""


_VISION_PROMPT = """You are reading an artifact submitted as evidence for a SOC 2 control.

Control {control_id} — {control_name}
Criterion: {control_text}

Describe ONLY what is visibly present. Extract concrete values (counts,
toggles, dates, usernames, policy names). If the artifact is unreadable,
cropped, or does not show the relevant setting, say so plainly and set
supports_control to false — a compliance reviewer relying on a confident
misread is worse than one who is told the evidence is inadequate.

Return JSON only:
{{"claim": "...", "supports_control": true, "observed_values": {{}},
  "confidence": 0.0, "caveats": ""}}
"""


async def parse_visual_evidence(
    data: bytes,
    kind: MediaKind,
    control: Control,
    *,
    agent: str = "hunter/infra",
    trace_id: str = "",
) -> VisualClaim:
    """Turn a screenshot / PDF / recording into a structured, checkable claim."""
    if not model_available():
        return VisualClaim(
            claim="Vision parsing unavailable — no model credentials configured.",
            supports_control=False,
            confidence=0.0,
            caveats="Artifact stored unparsed; a human must review it.",
            model="unavailable",
        )

    with identity.assume(agent):
        with span("gemini.vision", agent=agent, trace_id=trace_id,
                  model=settings.model_fast, media=kind, bytes=len(data)) as sp:
            try:
                from google.genai import types

                client = build_genai_client()

                prompt = _VISION_PROMPT.format(
                    control_id=control.id,
                    control_name=control.name,
                    control_text=control.text or control.name,
                )
                response = client.models.generate_content(
                    model=settings.model_fast,
                    contents=[
                        types.Part.from_bytes(data=data, mime_type=_MIME[kind]),
                        types.Part(text=prompt),
                    ],
                    config=types.GenerateContentConfig(temperature=0.0),
                )
                parsed = parse_json(response.text or "")
                sp.attributes["supports_control"] = parsed.get("supports_control")

                return VisualClaim(
                    claim=parsed.get("claim", ""),
                    supports_control=bool(parsed.get("supports_control")),
                    observed_values=parsed.get("observed_values", {}) or {},
                    confidence=float(parsed.get("confidence", 0.0)),
                    caveats=parsed.get("caveats", ""),
                    model=settings.model_fast,
                )
            except (ModelUnavailable, Exception) as exc:
                log.warning("vision parse failed (%s)", type(exc).__name__)
                return VisualClaim(
                    claim=f"Vision parsing failed: {type(exc).__name__}",
                    supports_control=False,
                    caveats="Artifact retained for human review.",
                    model="error",
                )


_BRIEFING_PROMPT = """Write a spoken morning briefing for Priya, the head of compliance.

Hard constraints:
- 45 seconds when read aloud (roughly 110-130 words).
- Lead with what changed overnight, not with pleasantries.
- Name specific controls and specific numbers.
- End with the single thing she should do today.
- No greeting, no sign-off, no markdown. Plain spoken prose.

Overnight state:
{state}
"""


async def daily_briefing(trace_id: str = "") -> dict[str, Any]:
    """Generate the spoken standup. Text always; audio when TTS is available."""
    store = get_store()
    controls: list[Control] = await store.list(CONTROLS, limit=5000)
    handoffs = [h for h in await store.list(HANDOFFS, limit=1000) if h.is_open]

    verified = [c for c in controls if c.status is ControlStatus.VERIFIED]
    stale = [c for c in controls if c.status is ControlStatus.STALE]
    failed = [c for c in controls if c.status is ControlStatus.FAILED]
    autonomous = [c for c in verified if c.closed_autonomously]

    state = (
        f"Verified: {len(verified)} of {len(controls)} controls "
        f"({round(len(verified) / max(1, len(controls)) * 100)}% ready).\n"
        f"Closed without any human involvement: {len(autonomous)} "
        f"({round(len(autonomous) / max(1, len(verified)) * 100)}% autonomy).\n"
        f"Drifted to stale: {', '.join(c.id for c in stale[:4]) or 'none'}.\n"
        f"Failing: {', '.join(c.id for c in failed[:4]) or 'none'}.\n"
        f"Waiting on Priya: "
        + (
            "; ".join(f"{h.control_id} — {h.question}" for h in handoffs[:3])
            or "nothing"
        )
    )

    script = ""
    if model_available():
        try:
            with span("gemini.briefing", agent="orchestrator", trace_id=trace_id,
                      model=settings.model_fast):
                from google.genai import types

                client = build_genai_client()
                response = client.models.generate_content(
                    model=settings.model_fast,
                    contents=_BRIEFING_PROMPT.format(state=state),
                    config=types.GenerateContentConfig(temperature=0.4),
                )
                script = (response.text or "").strip()
        except Exception as exc:
            log.info("briefing generation fell back (%s)", type(exc).__name__)

    if not script:
        # Deterministic fallback — still a real, useful briefing.
        blocker = handoffs[0] if handoffs else None

        def plural(n: int, one: str, many: str) -> str:
            return one if n == 1 else many

        script = (
            f"Overnight the fleet closed {len(autonomous)} "
            f"{plural(len(autonomous), 'control', 'controls')} without touching you. "
            f"You are at {round(len(verified) / max(1, len(controls)) * 100)} percent audit readiness, "
            f"{len(verified)} of {len(controls)} controls verified, "
            f"{round(len(autonomous) / max(1, len(verified)) * 100)} percent autonomous. "
            + (
                f"{len(stale)} {plural(len(stale), 'control has', 'controls have')} drifted stale, "
                f"starting with {stale[0].id}. "
                if stale
                else ""
            )
            + (
                f"{len(failed)} {plural(len(failed), 'is', 'are')} failing, "
                f"including {failed[0].id}. "
                if failed
                else ""
            )
            + (
                f"One thing needs you today: {blocker.control_id}. {blocker.question}"
                if blocker
                else "Nothing needs you today."
            )
        )

    audio_b64 = None
    if settings.is_cloud and settings.enable_tts:
        try:
            from google.cloud import texttospeech

            tts = texttospeech.TextToSpeechClient()
            audio = tts.synthesize_speech(
                input=texttospeech.SynthesisInput(text=script),
                voice=texttospeech.VoiceSelectionParams(
                    language_code="en-GB", name="en-GB-Studio-C"
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.02
                ),
            )
            audio_b64 = base64.b64encode(audio.audio_content).decode()
        except Exception as exc:  # pragma: no cover
            log.info("tts unavailable (%s); returning text only", type(exc).__name__)

    await emit(
        "orchestrator",
        "briefed",
        f"daily briefing generated · {len(script.split())} words",
        trace_id=trace_id,
    )

    return {
        "generated_at": now().isoformat(),
        "script": script,
        "word_count": len(script.split()),
        "estimated_seconds": round(len(script.split()) / 2.6),
        "audio_mp3_base64": audio_b64,
        "voiced": audio_b64 is not None,
        "model": settings.model_fast if model_available() else "deterministic-fallback",
    }


async def redact_locally(text: str) -> str:
    """Gemma 3 inside the trust boundary. Falls back to the regex redactor.

    This exists so a data-sovereign deployment never ships raw text to a
    hosted model just to strip a name out of it.
    """
    if settings.use_vertex_ai:
        try:
            from google import genai

            client = genai.Client(
                vertexai=True, project=settings.project_id, location=settings.location
            )
            response = client.models.generate_content(
                model=settings.model_redactor,
                contents=(
                    "Replace every piece of personal information with [REDACTED]. "
                    "Change nothing else. Return only the redacted text.\n\n" + text
                ),
            )
            if response.text:
                return response.text
        except Exception as exc:  # pragma: no cover
            log.info("gemma redactor unavailable (%s); using regex path", type(exc).__name__)

    from app.core.armor import _screen_local

    return _screen_local(text, "egress").text or text
