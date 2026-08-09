"""Dashboard (RA.4) + Metrics (RA.5): read-only analytics JSON for the frontend.

`GET /v1/dashboard` = feed + application-funnel + run outcomes. `GET /v1/metrics` = model
calls / cost / usage (durable, from the usage log + runs). Both deterministic and $0. The
unauthenticated Prometheus scrape endpoint stays at `/metrics` (see health router)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.security import require_token
from resumaker.analytics import dashboard_stats, metrics_overview

router = APIRouter(prefix="/v1", tags=["analytics"], dependencies=[Depends(require_token)])


@router.get("/dashboard")
def dashboard(days: int = 14) -> dict:
    return dashboard_stats(days=days)


@router.get("/metrics")
def metrics() -> dict:
    return metrics_overview()
