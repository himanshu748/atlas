"""ADK plumbing shared by the fleet.

Two things matter here:

1. Every agent is a real `google.adk.agents.LlmAgent` backed by
   `gemini-3.5-flash`. Orchestration uses ADK's Sequential/Parallel/Loop
   primitives rather than hand-rolled control flow.

2. The fleet degrades instead of dying. If no model credentials are present
   (a judge running `docker run` with no env), `invoke` falls back to a
   deterministic reasoner. The product still works end to end; the UI marks
   the ruling `model="deterministic-fallback"` so nobody is misled about
   what produced it.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Type

from pydantic import BaseModel

from app.config import settings

log = logging.getLogger("atlas.agents")

_APP_NAME = "atlas"
_session_service = None
_model_available: bool | None = None


def model_available() -> bool:
    """True when we can actually reach Gemini."""
    global _model_available
    if _model_available is None:
        _model_available = bool(
            settings.gemini_api_key
            or os.environ.get("GOOGLE_API_KEY")
            or settings.use_vertex_ai
        )
        log.info("model access: %s", "gemini-3.5-flash" if _model_available else "deterministic fallback")
    return _model_available


def build_genai_client():
    """Create a GenAI client for the configured backend."""
    from google import genai

    if settings.use_vertex_ai:
        return genai.Client(
            vertexai=True,
            project=settings.project_id,
            location=settings.location,
        )

    api_key = settings.gemini_api_key or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ModelUnavailable("no Gemini API key configured")
    return genai.Client(api_key=api_key)


def build_agent(
    name: str,
    instruction: str,
    *,
    model: str | None = None,
    tools: list[Any] | None = None,
    output_schema: Type[BaseModel] | None = None,
    description: str = "",
):
    """Construct an ADK LlmAgent. Names are ADK-safe (no slashes)."""
    from google.adk.agents import LlmAgent

    kwargs: dict[str, Any] = {
        "name": name.replace("/", "_").replace("-", "_"),
        "model": model or settings.model_fast,
        "instruction": instruction,
        "description": description or name,
    }
    if tools:
        kwargs["tools"] = tools
    if output_schema is not None:
        kwargs["output_schema"] = output_schema
        # ADK disallows transfer when a structured output is required.
        kwargs["disallow_transfer_to_parent"] = True
        kwargs["disallow_transfer_to_peers"] = True
    return LlmAgent(**kwargs)


def _get_session_service():
    global _session_service
    if _session_service is None:
        from google.adk.sessions import InMemorySessionService

        _session_service = InMemorySessionService()
    return _session_service


async def invoke(agent, prompt: str, *, user_id: str = "atlas", session_id: str | None = None) -> str:
    """Run an ADK agent to completion and return its final text output."""
    if not model_available():
        raise ModelUnavailable("no Gemini credentials configured")

    from google.adk.runners import Runner
    from google.genai import types

    session_service = _get_session_service()
    session_id = session_id or f"s-{agent.name}"
    try:
        await session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )
    except Exception:
        pass  # session already exists — fine, we reuse it

    runner = Runner(app_name=_APP_NAME, agent=agent, session_service=session_service)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    chunks: list[str] = []
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        content = getattr(event, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            if getattr(part, "text", None):
                chunks.append(part.text)
    return "".join(chunks).strip()


class ModelUnavailable(RuntimeError):
    """Raised when Gemini is not reachable; callers fall back deterministically."""


def parse_json(text: str) -> dict:
    """Extract a JSON object from a model response, tolerating fences/prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"no JSON object in model output: {text[:200]}")
