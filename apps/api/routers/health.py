"""Liveness + Prometheus metrics. Unauthenticated (safe, no PII) so a load balancer or
scraper can hit them."""
from __future__ import annotations

from fastapi import APIRouter, Response

from resumaker import __version__
from resumaker.observability import metrics

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/metrics")
def prometheus() -> Response:
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")
