"""Profile + preferences (read-only, non-PII summary). The canonical profile.json holds
contact PII, so the API exposes only counts/derived signals - never the raw contact block."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.security import require_token
from resumaker.enrichment import preferences
from resumaker.persistence import profile

router = APIRouter(prefix="/v1/profile", tags=["profile"], dependencies=[Depends(require_token)])


@router.get("/summary")
def summary() -> dict:
    return {
        "employers": sorted(profile.all_employers()),
        "titles": sorted(profile.all_titles()),
        "n_metrics": len(profile.all_metrics()),
        "n_skills": len(profile.all_skills()),
        "years_experience": profile.candidate_years(),
        "needs_sponsorship": profile.needs_sponsorship(),
        "preferences_configured": bool(preferences()),
    }
