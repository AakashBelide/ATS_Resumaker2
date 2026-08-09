"""Discovery feed (RA.1): a deterministic, LLM-free, resume-independent view over the
ingested `jobs`. Powers the frontend Discovery page. Real matching happens on add-to-Tracker
(RA.2), not here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.domain import JobRecord
from resumaker.ingestion import DiscoveryFilters, discover

router = APIRouter(prefix="/v1", tags=["discovery"], dependencies=[Depends(require_token)])


class DiscoveryOut(BaseModel):
    total: int
    jobs: list[JobRecord]
    facets: dict


def _csv(v: str | None) -> list[str] | None:
    """Parse a comma-separated multi-select param into a list (None/empty -> None)."""
    if not v:
        return None
    items = [x.strip() for x in v.split(",") if x.strip()]
    return items or None


@router.get("/discovery", response_model=DiscoveryOut)
def discovery(
    company: str | None = None,     # comma-separated for multi-select
    source: str | None = None,
    location: str | None = None,
    keyword: str | None = None,     # matches title or company
    since_days: int | None = None,
    on_target: bool = False,
    state: str | None = None,       # comma-separated (state codes / OTHER)
    level: str | None = None,       # comma-separated
    order: str = "recent",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DiscoveryOut:
    res = discover(DiscoveryFilters(
        company=_csv(company), source=source, location=location, keyword=keyword,
        since_days=since_days, on_target=on_target, state=_csv(state), level=_csv(level),
        order=order, limit=limit, offset=offset))
    return DiscoveryOut(total=res.total, jobs=res.jobs, facets=res.facets)
