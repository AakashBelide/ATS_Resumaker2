"""FastAPI application factory.

A modular monolith: one deployable app mounting the routers over the same `resumaker`
library the CLI uses. Startup configures logging and migrates SQLite; CORS is permissive
for the (same-owner) web dashboard + browser extension. Run:

    uv run uvicorn apps.api.main:app --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import costs, discovery, health, jobs, profile, runs
from resumaker import __version__
from resumaker.config import get_settings
from resumaker.observability.logging import configure_logging, get_logger
from resumaker.persistence import db

_log = get_logger("resumaker.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    db.init_db()
    s = get_settings()
    _log.info("api starting", extra={"version": __version__, "env": s.environment,
                                     "auth": bool(s.api_token), "scheduler": s.scheduler_enabled})
    scheduler = None
    if s.scheduler_enabled:
        from resumaker.ingestion.scheduler import build_scheduler
        scheduler = build_scheduler()
        scheduler.start()
        _log.info("watchlist scheduler started",
                  extra={"interval_min": s.scheduler_interval_minutes})
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="resumaker", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    for r in (health.router, runs.router, jobs.router, discovery.router,
              profile.router, costs.router):
        app.include_router(r)
    return app


app = create_app()
