"""Job watchlist + ingestion (RI seam, usable now without the scheduler).

Manage watched companies, list ingested postings, and trigger a one-off ingest that
lists a company's boards, dedupes into `jobs` ((source, external_id) + content_hash),
and reports what's new/changed. The scheduler (RI.3) will later call the same path on a
cadence.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.domain import BoardRef, Company, JobRecord
from resumaker.ingestion import ingest_company as _ingest
from resumaker.ingestion import resolve as _resolve
from resumaker.persistence import db
from resumaker.providers.sources import available_sources

router = APIRouter(prefix="/v1", tags=["jobs"], dependencies=[Depends(require_token)])


class CompanyIn(BaseModel):
    name: str
    boards: list[BoardRef]


class OnboardIn(BaseModel):
    name: str
    careers_url: str | None = None
    add: bool = True   # add to the watchlist if resolved


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


class ActiveIn(BaseModel):
    active: bool


@router.patch("/companies/{name}/active")
def set_company_active(name: str, body: ActiveIn) -> dict:
    """Pause/resume scraping for a company. Paused (active=false) companies are skipped by
    the ingest sweep; resuming picks up live postings from that point on (no backfill)."""
    if not db.set_company_active(name, body.active):
        raise HTTPException(404, "company not found")
    return {"name": name, "active": body.active}


@router.post("/onboard")
def onboard(body: OnboardIn) -> dict:
    """Auto-discover a company's board (slug-probe -> careers-page parse) and, if resolved
    and `add`, put it on the watchlist. Unresolved -> caller supplies careers_url/token."""
    res = _resolve(body.name, careers_url=body.careers_url)
    if res.resolved and body.add:
        db.add_company(Company(name=body.name, boards=res.boards))
    return {"name": res.name, "resolved": res.resolved, "method": res.method,
            "boards": [b.model_dump() for b in res.boards], "note": res.note,
            "tried": res.tried}


@router.get("/jobs", response_model=list[JobRecord])
def list_jobs(status: str | None = None, limit: int = 100) -> list[JobRecord]:
    return db.list_jobs(status=status, limit=limit)


@router.post("/companies/{name}/ingest")
def ingest_company(name: str, preferred_only: bool = False) -> dict:
    """List every board of the named company, dedupe into `jobs`, report counts."""
    companies = {c.name: c for c in db.list_companies(active_only=False)}
    if name not in companies:
        raise HTTPException(404, f"company '{name}' not on the watchlist")
    r = _ingest(companies[name], preferred_only=preferred_only)
    return {"company": r.company, "new_or_changed": r.new, "unchanged": r.unchanged,
            "errors": r.errors}
