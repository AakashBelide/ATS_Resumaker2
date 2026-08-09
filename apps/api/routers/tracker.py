"""Tracker (RA.2): jobs the owner is actively pursuing. Adding runs the match pipeline
(fit/gap/sponsorship/keywords, NO resume/cover); resume/cover stay a manual trigger. The
frontend Tracker page renders this + advances the application `stage`.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.domain import TrackerEntry
from resumaker.ingestion import tracker

router = APIRouter(prefix="/v1", tags=["tracker"], dependencies=[Depends(require_token)])


class TrackAddIn(BaseModel):
    job_id: int | None = None
    url: str | None = None
    run_match: bool = True


class StageIn(BaseModel):
    stage: str


class NotesIn(BaseModel):
    notes: str


@router.get("/tracker", response_model=list[TrackerEntry])
def list_tracked(stage: str | None = None) -> list[TrackerEntry]:
    return tracker.list_tracked(stage=stage)


@router.post("/tracker", response_model=TrackerEntry, status_code=201)
def add_tracked(body: TrackAddIn, background_tasks: BackgroundTasks) -> TrackerEntry:
    """Add a job (by watchlist `job_id` or raw `url`) INSTANTLY (stage=interested) and, when
    `run_match` (default), schedule the ~1-2 min match in the background so the '+Track' click
    never blocks. The entry appears immediately; fit/decision/sponsorship fill in shortly and
    show on the next Tracker refresh."""
    try:
        entry = tracker.add(job_id=body.job_id, url=body.url, run_match=False)
    except tracker.TrackerError as e:
        raise HTTPException(400, str(e)) from None
    if body.run_match and entry.id is not None:
        background_tasks.add_task(tracker.run_match_for, entry.id)
    return entry


@router.patch("/tracker/{entry_id}/stage", response_model=TrackerEntry)
def set_stage(entry_id: int, body: StageIn) -> TrackerEntry:
    try:
        return tracker.set_stage(entry_id, body.stage)
    except tracker.TrackerError as e:
        raise HTTPException(400, str(e)) from None


@router.patch("/tracker/{entry_id}/notes", response_model=TrackerEntry)
def set_notes(entry_id: int, body: NotesIn) -> TrackerEntry:
    try:
        return tracker.set_notes(entry_id, body.notes)
    except tracker.TrackerError as e:
        raise HTTPException(404, str(e)) from None


@router.delete("/tracker/{entry_id}")
def remove(entry_id: int) -> dict:
    return {"removed": tracker.remove(entry_id)}
