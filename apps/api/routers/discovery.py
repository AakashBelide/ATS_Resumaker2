"""Discovery feed (RA.1): a deterministic, LLM-free, resume-independent view over the
ingested `jobs`. Powers the frontend Discovery page. Real matching happens on add-to-Tracker
(RA.2), not here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.domain import JobRecord
from resumaker.ingestion import DiscoveryFilters, discover

router = APIRouter(prefix="/v1", tags=["discovery"], dependencies=[Depends(require_token)])


class DiscoveryOut(BaseModel):
    total: int
    jobs: list[JobRecord]
    facets: dict


@router.get("/discovery", response_model=DiscoveryOut)
def discovery(
    company: str | None = None,
    source: str | None = None,
    location: str | None = None,
    keyword: str | None = None,
    since_days: int | None = None,
    on_target: bool = False,
    order: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> DiscoveryOut:
    res = discover(DiscoveryFilters(
        company=company, source=source, location=location, keyword=keyword,
        since_days=since_days, on_target=on_target, order=order,
        limit=limit, offset=offset))
    return DiscoveryOut(total=res.total, jobs=res.jobs, facets=res.facets)
