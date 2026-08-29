"""Agent Identity — zero-trust scopes.

Each agent runs under its own SPIFFE identity with an explicit allowlist of
scopes. The IAM hunter physically cannot read HR records: not because the
prompt says so, but because `require_scope` raises before the connector is
reached, and in cloud mode the underlying service account lacks the IAM role.

This is the difference between "we told the model not to" and "the model
cannot".
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from app.config import settings

log = logging.getLogger("atlas.identity")


class ScopeDenied(PermissionError):
    """Raised when an agent reaches for a capability it was not granted."""


@dataclass(frozen=True)
class AgentIdentity:
    name: str
    scopes: frozenset[str] = field(default_factory=frozenset)

    @property
    def spiffe_id(self) -> str:
        slug = self.name.replace("/", "-")
        return f"spiffe://{settings.trust_domain}/agent/{slug}"

    def has(self, scope: str) -> bool:
        return scope in self.scopes


# The fleet's identity table. Mirrors the IAM bindings created by setup_gcp.sh.
IDENTITIES: dict[str, AgentIdentity] = {
    "orchestrator": AgentIdentity("orchestrator", frozenset({"registry.read", "fleet.delegate"})),
    "hunter/iam": AgentIdentity("hunter/iam", frozenset({"gcp.iam.read", "workspace.admin.read"})),
    "hunter/sdlc": AgentIdentity("hunter/sdlc", frozenset({"github.read"})),
    "hunter/infra": AgentIdentity("hunter/infra", frozenset({"gcp.asset.read", "gcp.logging.read"})),
    "hunter/hr": AgentIdentity("hunter/hr", frozenset({"hris.read.redacted"})),
    "hunter/vendor": AgentIdentity("hunter/vendor", frozenset({"drive.read"})),
    "judge": AgentIdentity("judge", frozenset({"ledger.read"})),
    "chaser": AgentIdentity("chaser", frozenset({"slack.write", "jira.write"})),
    "sentinel": AgentIdentity("sentinel", frozenset({"ledger.read", "pubsub.publish"})),
    "assembler": AgentIdentity("assembler", frozenset({"storage.write"})),
    "redactor": AgentIdentity("redactor", frozenset()),
}

_current: ContextVar[AgentIdentity | None] = ContextVar("atlas_identity", default=None)


def get(name: str) -> AgentIdentity:
    if name not in IDENTITIES:
        raise KeyError(f"unknown agent identity: {name}")
    return IDENTITIES[name]


def current() -> AgentIdentity | None:
    return _current.get()


@contextmanager
def assume(name: str):
    """Run a block under an agent's identity. Nesting is allowed and audited."""
    identity = get(name)
    token = _current.set(identity)
    try:
        yield identity
    finally:
        _current.reset(token)


def require_scope(scope: str) -> AgentIdentity:
    """Guard placed at the top of every connector call.

    Fails closed: no ambient identity means no access.
    """
    identity = _current.get()
    if identity is None:
        raise ScopeDenied(f"no agent identity in context; '{scope}' denied")
    if not identity.has(scope):
        log.warning("SCOPE DENIED %s wanted %s (has %s)", identity.name, scope, sorted(identity.scopes))
        raise ScopeDenied(
            f"{identity.spiffe_id} is not granted '{scope}' "
            f"(granted: {', '.join(sorted(identity.scopes)) or 'none'})"
        )
    return identity
