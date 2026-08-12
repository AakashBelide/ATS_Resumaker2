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


class MailerFilterIn(BaseModel):
    include: list[str] = []    # email a new posting only if its title has ANY of these
    exclude: list[str] = []    # ...and NONE of these (empty = no extra filtering)


class PreferencesIn(BaseModel):
    target_roles: list[str] = []   # on-target match keeps titles matching these
    avoid_roles: list[str] = []    # ...and drops titles matching these


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


@router.get("/mailer-filter", response_model=MailerFilterIn)
def get_mailer_filter() -> MailerFilterIn:
    """The email-digest title filter (editable). Only new on-target postings whose title passes
    this are emailed."""
    mf = profile.load_mailer_filter()
    return MailerFilterIn(include=mf.get("include") or [], exclude=mf.get("exclude") or [])


@router.put("/mailer-filter", response_model=MailerFilterIn)
def set_mailer_filter(body: MailerFilterIn) -> MailerFilterIn:
    profile.save_mailer_filter({"include": body.include, "exclude": body.exclude})
    return body


@router.get("/preferences", response_model=PreferencesIn)
def get_preferences() -> PreferencesIn:
    p = preferences()
    return PreferencesIn(target_roles=list(p.get("target_roles") or []),
                         avoid_roles=list(p.get("avoid_roles") or []))


@router.put("/preferences", response_model=PreferencesIn)
def set_preferences(body: PreferencesIn) -> PreferencesIn:
    """Edit the on-target role filter that drives Discovery + matching. Merges into the existing
    preferences doc so other keys (comp/location/work-model) are preserved."""
    prefs = dict(profile.load_preferences() or {})
    prefs["target_roles"] = [r.strip() for r in body.target_roles if r.strip()]
    prefs["avoid_roles"] = [r.strip() for r in body.avoid_roles if r.strip()]
    profile.save_preferences(prefs)
    return PreferencesIn(target_roles=prefs["target_roles"], avoid_roles=prefs["avoid_roles"])


@router.get("/proposals")
def proposals() -> dict:
    """Enrichment ideas mined from tracked jobs' gap reports (see enrichment.proposals)."""
    props = propose_from_tracker()
    return {k: [p.__dict__ for p in v] for k, v in props.items()}
