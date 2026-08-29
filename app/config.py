"""ATLAS configuration.

Every knob is env-driven so the same image runs locally (mock connectors,
in-memory store) and on Cloud Run (Firestore and Pub/Sub, with either the
Gemini Developer API or Vertex AI) with no code changes. This is deliberate:
judges must be able to `docker run` the container with zero credentials and
still see the product work.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- runtime mode ------------------------------------------------
    # local  : in-memory store, mock connectors, heuristic armor. No GCP needed.
    # cloud  : Firestore + Pub/Sub, with Gemini API or Vertex AI.
    mode: Literal["local", "cloud"] = Field("local", alias="ATLAS_MODE")

    # ---- google cloud ------------------------------------------------
    project_id: str = Field("", alias="GOOGLE_CLOUD_PROJECT")
    location: str = Field("us-central1", alias="GOOGLE_CLOUD_LOCATION")
    use_vertex: bool = Field(True, alias="GOOGLE_GENAI_USE_VERTEXAI")
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    use_managed_armor: bool = Field(True, alias="ATLAS_USE_MANAGED_ARMOR")
    enable_tts: bool = Field(False, alias="ATLAS_ENABLE_TTS")

    # ---- models ------------------------------------------------------
    model_fast: str = Field("gemini-3.5-flash", alias="ATLAS_MODEL_FAST")
    model_judge: str = Field("gemini-3.5-flash", alias="ATLAS_MODEL_JUDGE")
    model_redactor: str = Field("gemma-3-12b-it", alias="ATLAS_MODEL_REDACTOR")

    # ---- infra names -------------------------------------------------
    firestore_db: str = Field("(default)", alias="ATLAS_FIRESTORE_DB")
    topic_work: str = Field("atlas-work", alias="ATLAS_TOPIC_WORK")
    topic_events: str = Field("atlas-events", alias="ATLAS_TOPIC_EVENTS")
    bucket: str = Field("", alias="ATLAS_BUCKET")

    # ---- governance --------------------------------------------------
    armor_template_ingress: str = Field("atlas-ingress-strict", alias="ATLAS_ARMOR_INGRESS")
    armor_template_egress: str = Field("atlas-egress-pii", alias="ATLAS_ARMOR_EGRESS")
    trust_domain: str = Field("atlas.dev", alias="ATLAS_TRUST_DOMAIN")

    # ---- budget governor --------------------------------------------
    run_budget_usd: float = Field(50.0, alias="ATLAS_RUN_BUDGET_USD")
    estimated_cost_per_control_usd: float = Field(
        0.0031, alias="ATLAS_COST_PER_CONTROL_USD"
    )
    max_handoff_hours: int = Field(72, alias="ATLAS_HANDOFF_SLA_HOURS")

    # ---- connectors (optional; mocked when absent) -------------------
    github_token: str = Field("", alias="GITHUB_TOKEN")
    github_org: str = Field("", alias="GITHUB_ORG")
    slack_token: str = Field("", alias="SLACK_BOT_TOKEN")

    # ---- app ---------------------------------------------------------
    org_id: str = Field("acme", alias="ATLAS_ORG_ID")
    framework: str = Field("soc2", alias="ATLAS_FRAMEWORK")
    audit_window_weeks: int = Field(9, alias="ATLAS_AUDIT_WEEKS")

    @property
    def is_cloud(self) -> bool:
        return self.mode == "cloud" and bool(self.project_id)

    @property
    def use_vertex_ai(self) -> bool:
        """Use Vertex only when cloud mode explicitly requests it."""
        return self.is_cloud and self.use_vertex

    @property
    def use_ai_studio(self) -> bool:
        """Use the Gemini Developer API when an API key is configured."""
        return not self.use_vertex_ai and bool(
            self.gemini_api_key or os.environ.get("GOOGLE_API_KEY")
        )

    @property
    def model_backend(self) -> str:
        if self.use_vertex_ai:
            return "vertex-ai"
        if self.use_ai_studio:
            return "gemini-developer-api"
        return "deterministic-fallback"

    @property
    def memory_profile(self) -> str:
        return f"org/{self.org_id}/{self.framework}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Configure the backend that Google ADK and the GenAI SDK discover from env.
if settings.use_vertex_ai:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.project_id)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.location)
else:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
