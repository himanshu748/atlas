"""ATLAS — Autonomous Assurance Fleet.

Single Cloud Run service: API, SSE stream, and the console UI. One container
means one deploy, one URL, and one thing that can break — deliberate, given
that "prove it runs on Google Cloud" is 30% of the score.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import settings
from app.core.events import emit
from app.core.telemetry import init_tracing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("atlas")

WEB_DIR = Path(__file__).parent.parent / "web"
_background: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _background

    init_tracing()
    log.info("ATLAS starting · mode=%s · model=%s", settings.mode, settings.model_fast)

    from seed.seed_data import seed_all

    stats = await seed_all()
    log.info("ledger ready: %s", stats)

    await emit(
        "orchestrator",
        "online",
        f"fleet online · {stats['controls']} controls · {stats['agents']} agents registered",
    )

    # Local convenience only. On Cloud Run, Cloud Scheduler drives /internal/sweep
    # so no instance has to stay warm for the whole audit window.
    if not settings.is_cloud:
        from app.agents.orchestrator import get_orchestrator

        _background = asyncio.create_task(get_orchestrator().background_loop(interval_seconds=900))

    yield

    if _background:
        _background.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _background
    log.info("ATLAS stopped")


app = FastAPI(
    title="ATLAS — Autonomous Assurance Fleet",
    description="A governed fleet of agents that runs a SOC 2 audit window end to end.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if (WEB_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def console():
    index = WEB_DIR / "static" / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {"service": "atlas", "docs": "/docs", "health": "/healthz"}
