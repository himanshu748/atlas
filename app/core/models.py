"""ATLAS domain model.

The ledger is the spine of the product: every agent reads and writes
`Control` and `Evidence` documents, and every state change emits a
`FleetEvent`. Keeping these as strict Pydantic models means the same
shapes serialise to Firestore, to the SSE stream, and to the auditor's
export without translation layers.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


# ---------------------------------------------------------------- enums
class ControlStatus(str, Enum):
    IDLE = "idle"            # not yet attempted
    WORKING = "working"      # an agent is collecting right now
    WAITING = "waiting"      # blocked on a human handoff
    VERIFIED = "verified"    # judge ruled SATISFIED
    STALE = "stale"          # evidence aged past freshness SLA
    FAILED = "failed"        # judge ruled INSUFFICIENT, no path forward
    BLOCKED = "blocked"      # policy / armor denial


class Verdict(str, Enum):
    SATISFIED = "SATISFIED"
    INSUFFICIENT = "INSUFFICIENT"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class Domain(str, Enum):
    IAM = "iam"
    SDLC = "sdlc"
    INFRA = "infra"
    HR = "hr"
    VENDOR = "vendor"


class ArmorAction(str, Enum):
    PASS = "pass"
    REDACTED = "redacted"
    BLOCKED = "blocked"


class TaskState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    HALTED_ON_BUDGET = "halted_on_budget"


# ---------------------------------------------------------------- core
class Evidence(BaseModel):
    """A single artifact. Immutable once written; supersede, never edit."""

    id: str = Field(default_factory=lambda: new_id("ev"))
    control_id: str
    name: str
    kind: Literal["json", "pdf", "image", "video", "csv", "text"] = "json"
    source_system: str                      # e.g. "gcp.iam", "github"
    collected_by: str                       # agent name
    agent_identity: str                     # SPIFFE id — chain of custody hop 2
    collected_at: datetime = Field(default_factory=now)
    freshness_days: int = 90                # control-specific SLA
    sha256: str = ""
    armor_verdict: ArmorAction = ArmorAction.PASS
    size_bytes: int = 0
    summary: str = ""                       # what the agent extracted
    payload_ref: str = ""                   # gs:// or local path
    superseded_by: str | None = None

    @staticmethod
    def hash_payload(payload: str | bytes) -> str:
        data = payload.encode() if isinstance(payload, str) else payload
        return hashlib.sha256(data).hexdigest()

    @property
    def is_stale(self) -> bool:
        return now() - self.collected_at > timedelta(days=self.freshness_days)

    @property
    def age_days(self) -> int:
        return (now() - self.collected_at).days


class Ruling(BaseModel):
    """A Control Judge decision. Always cited, always traceable."""

    verdict: Verdict
    confidence: float = 0.0
    reasoning: str = ""
    cited_evidence: list[str] = Field(default_factory=list)
    blocking_question: str | None = None
    memories_used: list[str] = Field(default_factory=list)
    ruled_at: datetime = Field(default_factory=now)
    trace_id: str = ""
    model: str = ""


class Control(BaseModel):
    """One requirement in the framework. The unit the whole fleet works on."""

    id: str                                  # "CC6.1"
    group: str                               # "CC6"
    name: str
    text: str = ""                           # the actual criterion language
    domain: Domain = Domain.IAM
    owner: str = "unassigned"
    status: ControlStatus = ControlStatus.IDLE
    evidence_required: int = 3
    evidence_ids: list[str] = Field(default_factory=list)
    freshness_days: int = 90
    ruling: Ruling | None = None
    handoff_id: str | None = None
    human_touches: int = 0                   # powers the autonomy metric
    updated_at: datetime = Field(default_factory=now)
    updated_by: str = "system"

    @property
    def evidence_count(self) -> int:
        return len(self.evidence_ids)

    @property
    def coverage(self) -> float:
        if self.evidence_required == 0:
            return 1.0
        return min(1.0, self.evidence_count / self.evidence_required)

    @property
    def closed_autonomously(self) -> bool:
        return self.status == ControlStatus.VERIFIED and self.human_touches == 0


class Handoff(BaseModel):
    """The only place the fleet asks a human for anything."""

    id: str = Field(default_factory=lambda: new_id("HO"))
    control_id: str
    question: str
    reasoning: str = ""
    candidate_evidence: list[str] = Field(default_factory=list)
    recommendation: str = ""
    stage: int = 1                           # 1=owner 2=manager 3=at-risk
    opened_at: datetime = Field(default_factory=now)
    sla_hours: int = 72
    answered_at: datetime | None = None
    answer: Literal["approved", "rejected"] | None = None
    answer_reason: str = ""

    @property
    def is_open(self) -> bool:
        return self.answered_at is None

    @property
    def hours_remaining(self) -> float:
        deadline = self.opened_at + timedelta(hours=self.sla_hours)
        return max(0.0, (deadline - now()).total_seconds() / 3600)


class ArmorVerdict(BaseModel):
    """A Model Armor screening result. Surfaced as a product feature."""

    id: str = Field(default_factory=lambda: new_id("armor"))
    direction: Literal["ingress", "egress"]
    artifact: str
    agent: str
    template: str
    action: ArmorAction
    matched_policy: str = ""
    confidence: float = 0.0
    backend: Literal[
        "model-armor",
        "model-armor+deterministic",
        "deterministic-fallback",
    ] = "deterministic-fallback"
    excerpt: str = ""                        # sanitised, for the UI
    at: datetime = Field(default_factory=now)
    trace_id: str = ""


class Memory(BaseModel):
    """A durable belief about this org. Survives sessions and audits."""

    id: str = Field(default_factory=lambda: new_id("mem"))
    text: str
    scope: str = "org"                       # org | control | person
    subject: str = ""                        # e.g. "CC6.1" or "priya"
    source_run: str = ""
    confidence: float = 0.6
    reinforced: int = 1
    created_at: datetime = Field(default_factory=now)
    last_used: datetime | None = None


class Task(BaseModel):
    """Idempotent unit of work. Key is deterministic so redelivery is safe."""

    key: str                                 # "{run}:{control}:{step}"
    run_id: str
    control_id: str
    step: str
    agent: str
    state: TaskState = TaskState.PENDING
    attempts: int = 0
    cursor: str = ""                         # resume point for crash recovery
    error: str = ""
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    @staticmethod
    def make_key(run_id: str, control_id: str, step: str) -> str:
        return f"{run_id}:{control_id}:{step}"


class FleetEvent(BaseModel):
    """One line in the live activity stream. Also the Pub/Sub payload."""

    id: str = Field(default_factory=lambda: new_id("evt"))
    at: datetime = Field(default_factory=now)
    agent: str
    kind: str                                # collected | ruled | nudged | blocked | ...
    message: str
    control_id: str | None = None
    severity: Literal["info", "warn", "alert"] = "info"
    trace_id: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentCard(BaseModel):
    """Registry entry — how other departments discover and invoke an agent."""

    name: str
    version: str
    framework: str = "ADK 2"
    description: str
    spiffe_id: str
    scopes: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    invocations: int = 0
    endpoint: str = ""
    active: bool = True


class RunSummary(BaseModel):
    """Fleet-level posture. Everything the Command screen needs, in one doc."""

    run_id: str
    started_at: datetime
    controls_total: int = 0
    controls_verified: int = 0
    controls_autonomous: int = 0
    handoffs_open: int = 0
    events_emitted: int = 0
    cost_usd: float = 0.0
    budget_usd: float = 50.0
    dlq_depth: int = 0
    halted: bool = False

    @property
    def readiness_pct(self) -> int:
        if not self.controls_total:
            return 0
        return round(self.controls_verified / self.controls_total * 100)

    @property
    def autonomy_pct(self) -> int:
        if not self.controls_verified:
            return 100
        return round(self.controls_autonomous / self.controls_verified * 100)

    @property
    def uptime_seconds(self) -> int:
        return int((now() - self.started_at).total_seconds())
