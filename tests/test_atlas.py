"""Smoke tests for the pieces most likely to silently rot.

Run: pytest -q
"""
from __future__ import annotations

import pytest

from app.core import identity
from app.core.armor import _screen_local
from app.core.models import ArmorAction, Control, ControlStatus, Domain, Evidence, Task


# --------------------------------------------------------------- config
def test_cloud_mode_can_use_ai_studio_without_vertex():
    from app.config import Settings

    configured = Settings(
        ATLAS_MODE="cloud",
        GOOGLE_CLOUD_PROJECT="atlas-demo",
        GOOGLE_GENAI_USE_VERTEXAI=False,
        GEMINI_API_KEY="test-key",
    )
    assert configured.is_cloud
    assert configured.use_ai_studio
    assert not configured.use_vertex_ai


def test_zero_cost_profile_accepts_zero_budget_and_unit_cost():
    from app.config import Settings

    configured = Settings(
        ATLAS_RUN_BUDGET_USD=0,
        ATLAS_COST_PER_CONTROL_USD=0,
    )
    assert configured.run_budget_usd == 0
    assert configured.estimated_cost_per_control_usd == 0


# ---------------------------------------------------------------- identity
def test_scope_denied_without_identity():
    with pytest.raises(identity.ScopeDenied):
        identity.require_scope("gcp.iam.read")


def test_iam_hunter_cannot_read_hr():
    with identity.assume("hunter/iam"):
        identity.require_scope("gcp.iam.read")  # granted
        with pytest.raises(identity.ScopeDenied):
            identity.require_scope("hris.read.redacted")  # not granted


def test_spiffe_format():
    assert identity.get("judge").spiffe_id.startswith("spiffe://")


# ------------------------------------------------------------------ armor
def test_blocks_the_vendor_injection():
    from app.connectors.sources import _POISONED_SOC2

    result = _screen_local(_POISONED_SOC2, "ingress")
    assert result.action is ArmorAction.BLOCKED
    assert not result.allowed
    assert "injection" in result.policy


def test_clean_document_passes():
    result = _screen_local("Quarterly access review completed on 2026-07-01.", "ingress")
    assert result.action is ArmorAction.PASS


def test_pii_redacted_on_egress():
    result = _screen_local("Contact dev@acme.io, SSN 123-45-6789", "egress")
    assert result.action is ArmorAction.REDACTED
    assert "dev@acme.io" not in result.text
    assert "123-45-6789" not in result.text


# ---------------------------------------------------------------- ledger
def test_evidence_hash_is_stable():
    assert Evidence.hash_payload("x") == Evidence.hash_payload("x")
    assert Evidence.hash_payload("x") != Evidence.hash_payload("y")


def test_autonomy_requires_zero_human_touches():
    c = Control(id="CC6.1", group="CC6", name="t", domain=Domain.IAM,
                status=ControlStatus.VERIFIED, human_touches=0)
    assert c.closed_autonomously
    c.human_touches = 1
    assert not c.closed_autonomously


def test_task_key_is_deterministic():
    a = Task.make_key("run1", "CC6.1", "hunt")
    b = Task.make_key("run1", "CC6.1", "hunt")
    assert a == b == "run1:CC6.1:hunt"


# ----------------------------------------------------------- idempotency
@pytest.mark.asyncio
async def test_claim_task_is_idempotent():
    from app.core.store import claim_task, complete_task

    first = await claim_task("runX", "CC6.1", "hunt", "orchestrator")
    assert first is not None
    second = await claim_task("runX", "CC6.1", "hunt", "orchestrator")
    assert second is None, "redelivery must not re-run completed work"
    await complete_task(first)
    third = await claim_task("runX", "CC6.1", "hunt", "orchestrator")
    assert third is None


# --------------------------------------------------------------- memory
@pytest.mark.asyncio
async def test_memory_reinforces_instead_of_duplicating():
    from app.core.memory import memory_bank

    a = await memory_bank.remember("Priya requires exported JSON for CC6.1 access reviews.")
    b = await memory_bank.remember("Priya requires exported JSON for CC6.1 access reviews.")
    assert a.id == b.id
    assert b.reinforced >= 2


@pytest.mark.asyncio
async def test_memory_recall_prefers_exact_subject():
    from app.core.memory import memory_bank

    await memory_bank.remember("Break-glass permitted if reviewed within 24h.", subject="CC6.1")
    found = await memory_bank.recall("break-glass contractor access", subject="CC6.1")
    assert found and any("break-glass" in m.text.lower() for m in found)
