"""Tracker (RA.2): the jobs the owner is actively pursuing.

Adding a job runs the MATCH pipeline (`run_pipeline(..., match_only=True)`): scrape ->
structure -> keywords|gap|sponsorship -> fit -> apply-decision, and NOTHING after it. No
resume, no cover letter - those stay a deliberate manual trigger. We store the outcome
(fit, apply recommendation, sponsorship verdict) + a pointer to the match run's artifacts,
and an application `stage` the owner advances over time. Cost is bounded (one match run per
add, Claude CLI subscription by default) - the whole point of not scoring the entire feed.
"""
from __future__ import annotations

from pathlib import Path

from resumaker.domain import TRACKER_STAGES, TrackerEntry
from resumaker.observability.logging import get_logger
from resumaker.persistence import db

_log = get_logger("resumaker.tracker")


class TrackerError(ValueError):
    """Bad add (no target found) or invalid stage transition."""


def _apply_match(entry: TrackerEntry) -> None:
    """Run the match pipeline for a tracked entry and populate its match fields in place. On any
    failure (pipeline error or exception) we record `match_error` so the UI shows a 'failed' state
    (retryable) instead of an eternal 'matching…' - the row is the source of truth, so a failed
    match must be visibly distinct from one still in flight."""
    from resumaker.pipeline import run_pipeline
    try:
        res = run_pipeline(url=entry.url, match_only=True)
    except Exception as e:  # noqa: BLE001 - surface any crash as a retryable failed state
        _log.warning("tracker match crashed", extra={"url": entry.url, "error": str(e)})
        entry.match_error = str(e)
        entry.fit_0_100 = None
        entry.recommend_apply = None
        return
    if res.job is not None:                       # prefer the structured JD's fields
        entry.company = res.job.company or entry.company
        entry.title = res.job.title or entry.title
    if res.error:
        _log.warning("tracker match failed", extra={"url": entry.url, "error": res.error})
        entry.match_error = res.error
        entry.fit_0_100 = None
        entry.recommend_apply = None
        return
    entry.match_error = None                       # success: clear any prior failure
    entry.fit_0_100 = res.fit.final_0_100 if res.fit else None
    entry.recommend_apply = res.decision.recommend_apply if res.decision else None
    entry.sponsorship = (res.sponsorship or {}).get("verdict", "") if res.sponsorship else ""
    entry.run_id = Path(res.out_dir).name if res.out_dir else ""


def add(*, job_id: int | None = None, url: str | None = None,
        run_match: bool = True) -> TrackerEntry:
    """Add a job to the tracker. Provide either a watchlist `job_id` (from Discovery) or a raw
    `url`. `run_match=True` runs the (slow, ~1-2 min) match inline - the CLI uses that; the API
    adds instantly with `run_match=False` and schedules `run_match_for` in the background so
    the '+Track' click never blocks. Re-adding the same url preserves `stage`/`notes`."""
    company = title = ""
    resolved_job_id = job_id
    target_url = url or ""
    if job_id is not None:
        job = db.get_job(job_id)
        if job is None:
            raise TrackerError(f"job id {job_id} not found")
        target_url, company, title = job.url, job.company, job.title
    if not target_url:
        raise TrackerError("add() needs a job_id or a url")

    entry = TrackerEntry(job_id=resolved_job_id, url=target_url, company=company, title=title)
    if run_match:
        _apply_match(entry)
    entry.id = db.upsert_tracker(entry)
    _log.info("tracked", extra={"url": target_url, "fit": entry.fit_0_100,
                                "apply": entry.recommend_apply})
    return db.get_tracker(entry.id) or entry


def run_match_for(entry_id: int) -> None:
    """(Re)run the match for an existing tracked entry and persist the result. Safe to call in
    a background task after an instant add; preserves stage/notes via upsert (keyed on url)."""
    entry = db.get_tracker(entry_id)
    if entry is None:
        return
    _apply_match(entry)
    db.upsert_tracker(entry)


def clear_match_error(entry_id: int) -> TrackerEntry | None:
    """Clear a failed entry's `match_error` so the UI flips from 'failed' back to 'matching…'
    before a retry runs. Returns the updated entry, or None if it doesn't exist."""
    entry = db.get_tracker(entry_id)
    if entry is None:
        return None
    entry.match_error = None
    db.upsert_tracker(entry)
    return db.get_tracker(entry_id)


def set_stage(entry_id: int, stage: str) -> TrackerEntry:
    if stage not in TRACKER_STAGES:
        raise TrackerError(f"invalid stage {stage!r}; one of {TRACKER_STAGES}")
    if not db.set_tracker_stage(entry_id, stage):
        raise TrackerError(f"tracker entry {entry_id} not found")
    entry = db.get_tracker(entry_id)
    assert entry is not None
    return entry


def set_notes(entry_id: int, notes: str) -> TrackerEntry:
    if not db.set_tracker_notes(entry_id, notes):
        raise TrackerError(f"tracker entry {entry_id} not found")
    entry = db.get_tracker(entry_id)
    assert entry is not None
    return entry


def list_tracked(stage: str | None = None) -> list[TrackerEntry]:
    return db.list_tracker(stage=stage)


def remove(entry_id: int) -> int:
    return db.remove_tracker(entry_id)
