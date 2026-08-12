"""Email-digest controls (the Mailer page). One settings doc drives the notify pipeline:
title has/hasn't + seniority + US-state filters, quiet hours, a max-postings cap ("X of N"),
and the send frequency (which maps to Cloud Scheduler)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.api.security import require_token
from resumaker.ingestion.schedule_sync import FREQUENCIES, sync_mailer_frequency
from resumaker.persistence import profile

router = APIRouter(prefix="/v1/mailer", tags=["mailer"], dependencies=[Depends(require_token)])


class MailerPrefs(BaseModel):
    include: list[str] = []          # title has ANY of these
    exclude: list[str] = []          # ...and NONE of these
    levels: list[str] = []           # seniority levels to keep (empty = all)
    states: list[str] = []           # US state codes / "OTHER" (empty = all)
    quiet_enabled: bool = True       # False = never quiet (email 24/7), window ignored
    quiet_start: str = ""            # "HH:MM" local; empty pair = no quiet window
    quiet_end: str = ""
    timezone: str = "America/New_York"
    max_postings: int = Field(default=0, ge=0)   # 0 = no cap
    frequency: str = "hourly"


@router.get("/prefs", response_model=MailerPrefs)
def get_prefs() -> MailerPrefs:
    p = profile.load_mailer_prefs()
    return MailerPrefs(**{k: p[k] for k in MailerPrefs.model_fields if k in p})


@router.put("/prefs", response_model=MailerPrefs)
def set_prefs(body: MailerPrefs) -> MailerPrefs:
    data = body.model_dump()
    if data["frequency"] not in FREQUENCIES:
        data["frequency"] = "hourly"
    profile.save_mailer_prefs(data)                 # the prefs doc is the source of truth...
    sync_mailer_frequency(data["frequency"])        # ...then push the cadence to Cloud Scheduler
    return MailerPrefs(**data)


class MailerPreview(BaseModel):
    on_target: int      # stored postings in the owner's target roles (the denominator)
    matching: int       # ...that also pass the current title/level/state filter
    cap: int            # max_postings (0 = no cap)
    would_send: int     # how many a digest would include now: min(cap, matching) or matching


@router.post("/preview", response_model=MailerPreview)
def preview(body: MailerPrefs) -> MailerPreview:
    """Live 'X of N' for the Mailer page: count how many stored on-target postings the given
    (possibly unsaved) filter matches, so the owner can tune filters and see the effect."""
    from resumaker.ingestion.notify import preview_counts
    return MailerPreview(**preview_counts(body.model_dump()))
