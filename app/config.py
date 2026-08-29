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

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- runtime mode ------------------------------------------------
    # local  : in-memory store, mock connectors, heuristic armor. No GCP needed.
    # cloud  : Firestore + Pub/Sub, with Gemini API or Vertex AI.
    mode: Literal["local", "cloud"] = Field("local", alias="ATLAS_MODE")
    public_demo: bool = Field(False, alias="ATLAS_PUBLIC_DEMO")

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

    @model_validator(mode="after")
    def public_demo_is_explicitly_credential_free(self) -> "Settings":
        """Refuse to start a public fixture service with live capabilities.

        The public judge demo is a separate trust boundary. It must not become
        cloud-capable because a deploy accidentally carries an old variable or
        mounted credential forward.
        """
        if not self.public_demo:
            return self

        unsafe: list[str] = []
        if self.mode != "local":
            unsafe.append("ATLAS_MODE must be local")
        if self.project_id:
            unsafe.append("GOOGLE_CLOUD_PROJECT must be empty")
        if self.bucket:
            unsafe.append("ATLAS_BUCKET must be empty")
        if self.use_vertex:
            unsafe.append("GOOGLE_GENAI_USE_VERTEXAI must be false")
        if self.use_managed_armor:
            unsafe.append("ATLAS_USE_MANAGED_ARMOR must be false")
        if self.enable_tts:
            unsafe.append("ATLAS_ENABLE_TTS must be false")
        if self.run_budget_usd != 0:
            unsafe.append("ATLAS_RUN_BUDGET_USD must be 0")
        if self.estimated_cost_per_control_usd != 0:
            unsafe.append("ATLAS_COST_PER_CONTROL_USD must be 0")

        parsed_credentials = {
            "GEMINI_API_KEY": self.gemini_api_key,
            "GITHUB_TOKEN": self.github_token,
            "SLACK_BOT_TOKEN": self.slack_token,
        }
        present_parsed = [name for name, value in parsed_credentials.items() if value]
        if present_parsed:
            unsafe.append(f"credential settings present: {', '.join(present_parsed)}")

        credential_envs = (
            "GOOGLE_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "DEEPGRAM_API_KEY",
        )
        present_credentials = [name for name in credential_envs if os.environ.get(name)]
        if present_credentials:
            unsafe.append(f"credential variables present: {', '.join(present_credentials)}")

        if unsafe:
            raise ValueError("unsafe public demo configuration: " + "; ".join(unsafe))
        return self

    @property
    def is_cloud(self) -> bool:
        return not self.public_demo and self.mode == "cloud" and bool(self.project_id)

    @property
    def use_vertex_ai(self) -> bool:
        """Use Vertex only when cloud mode explicitly requests it."""
        return not self.public_demo and self.is_cloud and self.use_vertex

    @property
    def use_ai_studio(self) -> bool:
        """Use the Gemini Developer API when an API key is configured."""
        return not self.public_demo and not self.use_vertex_ai and bool(
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
