"""Route-level proof that scheduled drift is processed in the same request."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes


def test_internal_sweep_detects_drift_before_orchestration(monkeypatch) -> None:
    calls: list[str] = []

    async def detect_drift(run_id: str, trace_id: str) -> dict[str, int]:
        calls.append("sentinel")
        return {"stale": 1, "regressed": 0, "escalated": 0}

    class RecordingOrchestrator:
        async def run_sweep(self):
            assert calls == ["sentinel"]
            calls.append("orchestrator")
            return SimpleNamespace(readiness_pct=73.5)

    monkeypatch.setattr(routes.chaser, "sweep", detect_drift)
    monkeypatch.setattr(routes, "get_orchestrator", lambda: RecordingOrchestrator())
    app = FastAPI()
    app.include_router(routes.router)

    response = TestClient(app).post("/internal/sweep")

    assert response.status_code == 200
    assert response.json() == {
        "readiness_pct": 73.5,
        "stale": 1,
        "regressed": 0,
        "escalated": 0,
    }
    assert calls == ["sentinel", "orchestrator"]
