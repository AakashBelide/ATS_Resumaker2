"""Job watchlist + ingestion (RI seam, usable now without the scheduler).

Manage watched companies, list ingested postings, and trigger a one-off ingest that
lists a company's boards, dedupes into `jobs` ((source, external_id) + content_hash),
and reports what's new/changed. The scheduler (RI.3) will later call the same path on a
cadence.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.domain import BoardRef, Company, JobRecord
from resumaker.persistence import cache, db
from resumaker.providers.sources import available_sources, get_source

router = APIRouter(prefix="/v1", tags=["jobs"], dependencies=[Depends(require_token)])


class CompanyIn(BaseModel):
    name: str
    boards: list[BoardRef]


@router.get("/sources")
def sources() -> dict:
    return {"sources": available_sources()}


@router.get("/companies", response_model=list[Company])
def list_companies() -> list[Company]:
    return db.list_companies(active_only=False)


@router.post("/companies", status_code=201)
def add_company(body: CompanyIn) -> dict:
    cid = db.add_company(Company(name=body.name, boards=body.boards))
    return {"id": cid, "name": body.name, "boards": len(body.boards)}


@router.get("/jobs", response_model=list[JobRecord])
def list_jobs(status: str | None = None, limit: int = 100) -> list[JobRecord]:
    return db.list_jobs(status=status, limit=limit)


@router.post("/companies/{name}/ingest")
def ingest_company(name: str) -> dict:
    """List every board of the named company, dedupe postings into `jobs`, and report
    new/changed/seen counts. Idempotent - safe to call repeatedly."""
    companies = {c.name: c for c in db.list_companies(active_only=False)}
    if name not in companies:
        return {"error": f"company '{name}' not on the watchlist"}
    new = seen = 0
    for board in companies[name].boards:
        for stub in get_source(board.source).list_postings(board.token):
            content_hash = cache.make_key(stub.title, stub.location, stub.updated_at)
            _, is_new_or_changed = db.upsert_job(JobRecord(
                source=stub.source, external_id=stub.external_id, url=stub.url,
                title=stub.title, company=name, location=stub.location,
                content_hash=content_hash))
            if is_new_or_changed:
                new += 1
            else:
                seen += 1
    return {"company": name, "new_or_changed": new, "unchanged": seen}
