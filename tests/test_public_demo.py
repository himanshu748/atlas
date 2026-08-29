"""Fail-closed tests for the anonymous, fixture-only judge surface."""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import WEB_DIR, create_app, public_demo_request_allowed, should_start_background


SECRET_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GITHUB_TOKEN",
    "SLACK_BOT_TOKEN",
    "DEEPGRAM_API_KEY",
)


@pytest.fixture
def public_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return Settings(
        ATLAS_MODE="local",
        ATLAS_PUBLIC_DEMO=True,
        GOOGLE_CLOUD_PROJECT="",
        GOOGLE_GENAI_USE_VERTEXAI=False,
        GEMINI_API_KEY="",
        ATLAS_USE_MANAGED_ARMOR=False,
        ATLAS_ENABLE_TTS=False,
        ATLAS_BUCKET="",
        ATLAS_RUN_BUDGET_USD=0,
        ATLAS_COST_PER_CONTROL_USD=0,
        GITHUB_TOKEN="",
        SLACK_BOT_TOKEN="",
    )


def test_public_demo_requires_every_live_capability_to_be_explicitly_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError, match="unsafe public demo configuration"):
        Settings(ATLAS_PUBLIC_DEMO=True)

    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-be-mounted")
    with pytest.raises(ValidationError, match="GOOGLE_API_KEY"):
        Settings(
            ATLAS_MODE="local",
            ATLAS_PUBLIC_DEMO=True,
            GOOGLE_GENAI_USE_VERTEXAI=False,
            ATLAS_USE_MANAGED_ARMOR=False,
            ATLAS_RUN_BUDGET_USD=0,
            ATLAS_COST_PER_CONTROL_USD=0,
        )

    monkeypatch.delenv("GOOGLE_API_KEY")
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(
            ATLAS_MODE="local",
            ATLAS_PUBLIC_DEMO=True,
            GOOGLE_GENAI_USE_VERTEXAI=False,
            ATLAS_USE_MANAGED_ARMOR=False,
            ATLAS_RUN_BUDGET_USD=0,
            ATLAS_COST_PER_CONTROL_USD=0,
            GEMINI_API_KEY="must-not-load-from-dotenv-either",
        )


def test_public_demo_has_no_cloud_or_model_backend(public_settings: Settings) -> None:
    assert public_settings.public_demo
    assert not public_settings.is_cloud
    assert not public_settings.use_vertex_ai
    assert not public_settings.use_ai_studio
    assert public_settings.model_backend == "deterministic-fallback"
    assert not should_start_background(public_settings)


def test_public_allowlist_is_narrow_and_method_safe() -> None:
    for path in (
        "/",
        "/healthz",
        "/api/fleet",
        "/api/controls",
        "/api/controls/CC6.1",
        "/api/traces/example",
        "/static/app.js",
    ):
        assert public_demo_request_allowed("GET", path)

    for path in (
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/stream",
        "/api/briefing",
        "/api/handoffs",
        "/internal/sweep",
    ):
        assert not public_demo_request_allowed("GET", path)

    assert not public_demo_request_allowed("POST", "/api/fleet")
    assert not public_demo_request_allowed("OPTIONS", "/api/fleet")


def test_public_app_blocks_every_stateful_or_expensive_route(
    public_settings: Settings,
) -> None:
    client = TestClient(create_app(public_settings))
    blocked = (
        ("post", "/api/sweep", {"json": {"limit_per_domain": 1}}),
        ("post", "/api/handoffs/DEMO-HO-1/answer", {"json": {"answer": "approved"}}),
        ("post", "/api/memories/recall", {"json": {"query": "anything"}}),
        ("post", "/api/package", {"json": {}}),
        ("post", "/api/controls/CC6.1/visual-evidence", {"files": {"file": ("x.txt", b"x")}}),
        ("post", "/internal/sweep", {}),
        ("get", "/api/briefing", {}),
        ("get", "/api/stream", {}),
        ("get", "/docs", {}),
        ("get", "/redoc", {}),
        ("get", "/openapi.json", {}),
    )

    for method, path, kwargs in blocked:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, (method, path, response.text)
        if path.startswith(("/api/", "/internal/")):
            assert response.headers["cache-control"] == "no-store"


def test_public_app_sets_browser_headers_and_never_enables_cors(
    public_settings: Settings,
) -> None:
    client = TestClient(create_app(public_settings))
    response = client.get("/healthz", headers={"origin": "https://attacker.example"})

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert "access-control-allow-origin" not in response.headers


def test_local_docs_are_not_broken_by_the_public_only_csp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    local_settings = Settings(ATLAS_MODE="local", ATLAS_PUBLIC_DEMO=False)

    response = TestClient(create_app(local_settings)).get("/docs")

    assert response.status_code == 200
    assert "cdn.jsdelivr.net" in response.text
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_public_app_rate_limits_each_client_and_the_whole_instance(
    public_settings: Settings,
) -> None:
    with TestClient(create_app(public_settings)) as client:
        limiter = client.app.state.public_demo_rate_limiter
        limiter.per_client_limit = 2
        limiter.global_limit = 3

        assert client.get("/api/health", headers={"x-forwarded-for": "one, edge"}).status_code == 200
        assert client.get("/api/health", headers={"x-forwarded-for": "one, edge"}).status_code == 200
        client_limited = client.get(
            "/api/health", headers={"x-forwarded-for": "one, edge"}
        )
        assert client_limited.status_code == 429
        assert client_limited.headers["retry-after"] == "60"
        assert client_limited.headers["cache-control"] == "no-store"

        assert client.get("/api/health", headers={"x-forwarded-for": "two, edge"}).status_code == 200
        globally_limited = client.get(
            "/api/health", headers={"x-forwarded-for": "three, edge"}
        )
        assert globally_limited.status_code == 429


def test_public_fleet_read_does_not_persist_summary(
    public_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.store as store_module
    from seed.seed_data import seed_all

    store = store_module.MemoryStore()
    monkeypatch.setattr(store_module, "_store", store)
    asyncio.run(seed_all())
    before = asyncio.run(store.get(store_module.RUNS, "run-2026-q3"))
    before_dump = before.model_dump(mode="json") if before else None

    response = TestClient(create_app(public_settings)).get("/api/fleet")

    assert response.status_code == 200
    payload = response.json()
    assert payload["public_demo"] is True
    assert payload["read_only"] is True
    assert payload["data_profile"] == "seeded-fixtures"
    assert payload["runtime_mode"] == "local"
    assert payload["model_backend"] == "deterministic-fallback"
    assert payload["cloud_location"] is None
    after = asyncio.run(store.get(store_module.RUNS, "run-2026-q3"))
    assert (after.model_dump(mode="json") if after else None) == before_dump


def test_public_lifespan_seeds_a_representative_labelled_snapshot(
    public_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.events as events_module
    import app.core.store as store_module
    import app.core.telemetry as telemetry_module

    monkeypatch.setattr(store_module, "_store", store_module.MemoryStore())
    monkeypatch.setattr(events_module.broadcaster, "_recent", [])
    monkeypatch.setattr(telemetry_module.traces, "_traces", {})
    monkeypatch.setattr(telemetry_module.traces, "_order", [])

    with TestClient(create_app(public_settings)) as client:
        fleet = client.get("/api/fleet").json()
        armor = client.get("/api/armor").json()
        events = client.get("/api/events").json()
        traces = client.get("/api/traces").json()

    assert len(fleet["handoffs"]) == 2
    assert all(item["id"].startswith("FIXTURE-") for item in fleet["handoffs"])
    assert armor["counts"]["blocked"] == 1
    assert armor["verdicts"][0]["artifact"].startswith("fixture:")
    assert armor["verdicts"][0]["backend"] == "model-armor+deterministic"
    assert len(events) >= 4
    assert sum(item["meta"].get("fixture") is True for item in events) >= 4
    assert traces and traces[0]["trace_id"].startswith("fixture-")


def test_public_ui_escapes_fixture_text_and_exposes_no_event_stream() -> None:
    app_js = (WEB_DIR / "static" / "app.js").read_text()
    live_js = (WEB_DIR / "static" / "live.js").read_text()

    assert "escapeHtml(m.text)" in app_js
    assert "escapeHtml(e.m)" in app_js
    assert "if (!window.__atlasPublicDemo) connectStream();" in live_js
    assert "if (window.__atlasPublicDemo)" in live_js
    assert "if (workingCount)" in live_js
    assert "document.body.dataset.publicDemo === 'true'" in app_js
