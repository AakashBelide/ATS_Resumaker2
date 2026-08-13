"""Tracker (RA.2): jobs the owner is actively pursuing. Adding runs the match pipeline
(fit/gap/sponsorship/keywords, NO resume/cover); resume/cover stay a manual trigger. The
frontend Tracker page renders this + advances the application `stage`.
"""
from __future__ import annotations

import base64
import contextlib
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.jobs.queue import get_job_queue
from apps.api.security import require_token
from resumaker.domain import TrackerEntry
from resumaker.ingestion import tracker

router = APIRouter(prefix="/v1", tags=["tracker"], dependencies=[Depends(require_token)])

# Capture input caps (see `/tracker/capture`). The extension does the heavy lifting client-side,
# so the body is bounded: the JD text is small, the screenshot larger but still capped. Full-page
# shots of long postings can be sizeable (the extension sends JPEG for tall pages), so the cap is
# generous. `screenshot.png`/`screenshot.jpg` per the source mime; both are accepted + servable.
_MAX_RAW_TEXT = 200_000                 # ~200 KB cap on the captured JD text
_MAX_SHOT_BYTES = 15 * 1024 * 1024      # 15 MB cap on the decoded screenshot (full-page can be big)
_DATA_URL_RE = re.compile(r"^data:image/(png|jpeg);base64,(.+)$", re.DOTALL)


class TrackAddIn(BaseModel):
    job_id: int | None = None
    url: str | None = None
    run_match: bool = True


class TrackCaptureIn(BaseModel):
    """Browser-extension capture: the page's visible JD text + an optional screenshot data URL."""
    url: str
    raw_text: str
    title: str | None = None
    screenshot: str | None = None       # "data:image/(png|jpeg);base64,..." or null


class StageIn(BaseModel):
    stage: str


class NotesIn(BaseModel):
    notes: str


@router.get("/tracker", response_model=list[TrackerEntry])
def list_tracked(stage: str | None = None) -> list[TrackerEntry]:
    return tracker.list_tracked(stage=stage)


@router.get("/tracker/by-run/{run_id}", response_model=TrackerEntry)
def tracked_by_run(run_id: str) -> TrackerEntry:
    """The tracked entry for a match run, so the report page can show the authoritative ATS
    posting title/company. 404 when the run isn't a tracked job (e.g. an ad-hoc run)."""
    entry = tracker.get_by_run(run_id)
    if entry is None:
        raise HTTPException(404, "no tracked job for this run")
    return entry


@router.post("/tracker", response_model=TrackerEntry, status_code=201)
def add_tracked(body: TrackAddIn) -> TrackerEntry:
    """Add a job (by watchlist `job_id` or raw `url`) INSTANTLY (stage=interested) and, when
    `run_match` (default), run the ~1-2 min match off-request (locally on a thread; in cloud
    enqueued to the worker) so the '+Track' click never blocks. The entry appears immediately;
    fit/decision/sponsorship fill in shortly and
    show on the next Tracker refresh."""
    try:
        entry = tracker.add(job_id=body.job_id, url=body.url, run_match=False)
    except tracker.TrackerError as e:
        raise HTTPException(400, str(e)) from None
    if body.run_match and entry.id is not None:
        get_job_queue().submit_tracker_match(entry.id)
    return entry


def _validate_http_url(url: str) -> None:
    """Reject anything that isn't a well-formed http(s) URL (400)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise HTTPException(400, "url must be a valid http(s) URL")


def _decode_screenshot(data_url: str) -> tuple[str, bytes]:
    """Validate + decode a `data:image/(png|jpeg);base64,...` URL. Returns (filename, bytes) with the
    filename fixed to `screenshot.png` or `screenshot.jpg` per the source mime (basename only - no
    traversal). Size-capped; 400 on any violation. Never echoes the (large) body in the error."""
    m = _DATA_URL_RE.match(data_url.strip())
    if not m:
        raise HTTPException(400, "screenshot must be a data:image/(png|jpeg);base64 URL")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise HTTPException(400, "screenshot is not valid base64") from None
    if not raw:
        raise HTTPException(400, "screenshot is empty")
    if len(raw) > _MAX_SHOT_BYTES:
        raise HTTPException(400, "screenshot exceeds the size limit")
    name = "screenshot.jpg" if m.group(1) == "jpeg" else "screenshot.png"
    return name, raw


@router.post("/tracker/capture", response_model=TrackerEntry, status_code=201)
def capture_tracked(body: TrackCaptureIn) -> TrackerEntry:
    """Capture the CURRENT page as a tracked job (the browser-extension path). The extension already
    has the posting loaded, so it sends the visible JD `raw_text` (+ an optional `screenshot`) and
    the backend SKIPS server-side scraping: the match structures the captured text with the LLM,
    then runs the same match-only analysis (fit/gap/sponsorship/keywords) as a normal add.

    Flow: validate -> derive a stable run_id (so the screenshot + match report share one folder) ->
    store the screenshot in the artifact store -> create the entry INSTANTLY with the captured JD ->
    enqueue the match off-request so the click never blocks. Returns the created entry."""
    from resumaker.persistence import files

    text = (body.raw_text or "").strip()
    if not text:
        raise HTTPException(400, "raw_text must not be empty")
    if len(body.raw_text) > _MAX_RAW_TEXT:
        raise HTTPException(400, "raw_text exceeds the size limit")
    _validate_http_url(body.url)
    shot = _decode_screenshot(body.screenshot) if body.screenshot else None

    title = (body.title or "").strip()
    # Deterministic slug from the posting (title now; company fills in at match time). unique_key=url
    # keeps two same-titled postings from colliding on one run folder, and makes the screenshot land
    # in the SAME folder the match will reuse.
    run_id = files.run_slug(role=title, fallback=body.url, unique_key=body.url)

    if shot is not None:
        shot_name, shot_bytes = shot                            # screenshot.png | screenshot.jpg
        from resumaker.persistence.artifacts import get_artifact_store
        store = get_artifact_store()
        (store.local_run_dir(run_id) / shot_name).write_bytes(shot_bytes)
        with contextlib.suppress(Exception):                    # no-op locally; GCS upload in cloud
            store.publish(run_id)

    try:
        entry = tracker.capture(url=body.url, raw_text=body.raw_text, title=title, run_id=run_id)
    except tracker.TrackerError as e:
        raise HTTPException(400, str(e)) from None
    if entry.id is not None:
        get_job_queue().submit_tracker_match(entry.id)
    return entry


@router.post("/tracker/{entry_id}/rematch", response_model=TrackerEntry)
def rematch(entry_id: int) -> TrackerEntry:
    """Re-run the match for an entry (failed, or to refresh a stale report/title). Returns the
    entry immediately with `match_error` cleared so the UI flips back to 'matching…'; the match
    runs off-request (worker in cloud) and fills in fit/decision on the next poll."""
    entry = tracker.clear_match_error(entry_id)
    if entry is None:
        raise HTTPException(404, f"tracker entry {entry_id} not found")
    get_job_queue().submit_tracker_match(entry_id)
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
