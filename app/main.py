"""ATLAS — Autonomous Assurance Fleet.

Single Cloud Run service: API, SSE stream, and the console UI. One container
means one deploy, one URL, and one thing that can break — deliberate, given
that "prove it runs on Google Cloud" is 30% of the score.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

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

PUBLIC_DEMO_EXACT_GETS = frozenset(
    {
        "/",
        "/healthz",
        "/api/health",
        "/api/fleet",
        "/api/events",
        "/api/controls",
        "/api/agents",
        "/api/armor",
        "/api/memories",
        "/api/traces",
    }
)
PUBLIC_DEMO_DETAIL_GET = re.compile(r"^/api/(?:controls|traces)/[^/]+$")


class PublicDemoRateLimiter:
    """Small in-process brake for the single-instance anonymous judge surface."""

    def __init__(
        self,
        *,
        per_client_limit: int = 120,
        global_limit: int = 600,
        window_seconds: int = 60,
        max_clients: int = 2048,
    ) -> None:
        self.per_client_limit = per_client_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._global: deque[float] = deque()
        self._clients: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    @staticmethod
    def _prune(bucket: deque[float], cutoff: float) -> None:
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    async def allow(self, client_key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            self._prune(self._global, cutoff)
            if len(self._global) >= self.global_limit:
                return False

            bucket = self._clients.get(client_key)
            if bucket is None:
                while len(self._clients) >= self.max_clients:
                    self._clients.popitem(last=False)
                bucket = deque()
                self._clients[client_key] = bucket
            else:
                self._clients.move_to_end(client_key)
            self._prune(bucket, cutoff)
            if len(bucket) >= self.per_client_limit:
                return False

            bucket.append(now)
            self._global.append(now)
            return True


def public_demo_client_key(request: Request) -> str:
    """Use the client hop appended by the managed proxy when it is available."""
    forwarded = [
        part.strip()
        for part in request.headers.get("x-forwarded-for", "").split(",")
        if part.strip()
    ]
    if len(forwarded) >= 2:
        return forwarded[-2]
    if forwarded:
        return forwarded[0]
    return request.client.host if request.client else "unknown"


def public_demo_request_allowed(method: str, path: str) -> bool:
    """Return true only for the fixture reads required by the judge console."""
    if method not in {"GET", "HEAD"}:
        return False
    return (
        path in PUBLIC_DEMO_EXACT_GETS
        or path.startswith("/static/")
        or bool(PUBLIC_DEMO_DETAIL_GET.fullmatch(path))
    )


def should_start_background(runtime_settings=settings) -> bool:
    return not runtime_settings.is_cloud and not runtime_settings.public_demo


def add_security_headers(response, *, public_demo: bool = False) -> None:
    if public_demo:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'"
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"


def build_lifespan(runtime_settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        background: asyncio.Task | None = None

        init_tracing()
        log.info(
            "ATLAS starting · mode=%s · model=%s · public_demo=%s",
            runtime_settings.mode,
            runtime_settings.model_fast,
            runtime_settings.public_demo,
        )

        from seed.seed_data import seed_all

        stats = await seed_all()
        if runtime_settings.public_demo:
            from seed.public_demo import seed_public_demo_snapshot

            stats.update(await seed_public_demo_snapshot())
        log.info("ledger ready: %s", stats)

        await emit(
            "orchestrator",
            "online",
            f"fleet online · {stats['controls']} controls · {stats['agents']} agents registered",
        )

        # Local convenience only. The public demo must remain a passive fixture.
        if should_start_background(runtime_settings):
            from app.agents.orchestrator import get_orchestrator

            background = asyncio.create_task(
                get_orchestrator().background_loop(interval_seconds=900)
            )

        yield

        if background:
            background.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await background
        log.info("ATLAS stopped")

    return lifespan


def create_app(runtime_settings=settings) -> FastAPI:
    application = FastAPI(
        title="ATLAS — Autonomous Assurance Fleet",
        description="A governed fleet of agents that runs a SOC 2 audit window end to end.",
        version="1.0.0",
        lifespan=build_lifespan(runtime_settings),
        docs_url=None if runtime_settings.public_demo else "/docs",
        redoc_url=None if runtime_settings.public_demo else "/redoc",
        openapi_url=None if runtime_settings.public_demo else "/openapi.json",
    )
    application.state.settings = runtime_settings
    application.state.public_demo_rate_limiter = (
        PublicDemoRateLimiter() if runtime_settings.public_demo else None
    )

    if runtime_settings.public_demo:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*.run.app", "localhost", "127.0.0.1", "testserver"],
        )

    @application.middleware("http")
    async def request_boundary(request: Request, call_next):
        rate_limiter = application.state.public_demo_rate_limiter
        if rate_limiter and not await rate_limiter.allow(public_demo_client_key(request)):
            response = JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
            response.headers["Retry-After"] = str(rate_limiter.window_seconds)
            response.headers["Cache-Control"] = "no-store"
        elif runtime_settings.public_demo and not public_demo_request_allowed(
            request.method, request.url.path
        ):
            response = JSONResponse({"detail": "Not found"}, status_code=404)
        else:
            response = await call_next(request)

        if request.url.path.startswith("/api/") or request.url.path.startswith("/internal/"):
            response.headers["Cache-Control"] = "no-store"
        add_security_headers(response, public_demo=runtime_settings.public_demo)
        return response

    application.include_router(router)

    if (WEB_DIR / "static").is_dir():
        application.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @application.get("/", include_in_schema=False)
    async def console():
        index = WEB_DIR / "static" / "index.html"
        if index.is_file():
            if runtime_settings.public_demo:
                public_html = index.read_text(encoding="utf-8")
                public_html = public_html.replace(
                    "<body>", '<body class="public-demo" data-public-demo="true">', 1
                ).replace(
                    'aria-label="Public demo boundary" hidden',
                    'aria-label="Public demo boundary"',
                    1,
                )
                return HTMLResponse(public_html)
            return FileResponse(index)
        return {
            "service": "atlas",
            "docs": None if runtime_settings.public_demo else "/docs",
            "health": "/healthz",
        }

    return application


app = create_app()
