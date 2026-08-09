"""Profile + preferences + enrichment (RA.3). The canonical profile.json holds contact PII,
so the API exposes only derived signals (skills/titles/employers/counts) - never the raw
contact block. `PATCH /fact` folds an owner-provided fact into profile.json (audited)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.enrichment import preferences, propose_from_tracker, update_profile_fact
from resumaker.persistence import profile

router = APIRouter(prefix="/v1/profile", tags=["profile"], dependencies=[Depends(require_token)])


class FactIn(BaseModel):
    path: list[str | int]      # e.g. ["skills", "Languages"] or ["preferences", "location"]
    value: Any
    reason: str


@router.get("/summary")
def summary() -> dict:
    return {
        "employers": sorted(profile.all_employers()),
        "titles": sorted(profile.all_titles()),
        "skills": sorted(profile.all_skills()),
        "n_metrics": len(profile.all_metrics()),
        "n_skills": len(profile.all_skills()),
        "years_experience": profile.candidate_years(),
        "needs_sponsorship": profile.needs_sponsorship(),
        "preferences": preferences(),
    }


@router.patch("/fact")
def set_fact(body: FactIn) -> dict:
    """Fold an owner-provided fact into the canonical profile (audited in the enrichment log).
    Only for REAL facts the owner supplies - never fabrication."""
    old = update_profile_fact(list(body.path), body.value, body.reason)
    return {"path": body.path, "old": old, "new": body.value, "reason": body.reason}


@router.get("/proposals")
def proposals() -> dict:
    """Enrichment ideas mined from tracked jobs' gap reports (see enrichment.proposals)."""
    props = propose_from_tracker()
    return {k: [p.__dict__ for p in v] for k, v in props.items()}
