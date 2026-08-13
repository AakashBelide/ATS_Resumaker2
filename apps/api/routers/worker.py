"""Worker endpoints (D.3): the request-triggered halves of ingestion + pipeline execution.

Cloud Run services are request-based (no always-on process), so the two long-running jobs
can't live in an in-process loop there. This router exposes them as HTTP endpoints that an
external trigger invokes:

  - POST /v1/worker/ingest-tick   <- Cloud Scheduler (cron). One watchlist poll. Two Scheduler
                                     jobs map to `fast` (hourly) and `slow` (daily) source sets.
  - POST /v1/worker/run-pipeline  <- Cloud Tasks (work queue). Runs ONE pipeline synchronously
                                     (Cloud Run holds the request; Tasks retries on non-2xx).

Dual-mode: locally the in-process APScheduler still drives ticks and `/v1/runs` still runs in
the ThreadPoolExecutor - these endpoints are simply *also* callable (and are what the cloud
triggers hit). Same core functions either way (`run_tick`, `run_pipeline`), so behavior is
identical. Protected by the same single-user token; Cloud Scheduler/Tasks send it as a header.
"""
from __future__ import annotations

import contextlib
import json
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker.domain import GapReport, JobPosting, KeywordSet, RunRecord
from resumaker.observability.logging import get_logger
from resumaker.persistence import db
from resumaker.persistence.artifacts import get_artifact_store
from resumaker.pipeline import run_pipeline

_log = get_logger("resumaker.api.worker")

router = APIRouter(prefix="/v1/worker", tags=["worker"], dependencies=[Depends(require_token)])


class IngestTickIn(BaseModel):
    sources: str = "all"     # all | fast | slow (maps to the two poll cadences)


class IngestTickOut(BaseModel):
    sources: str
    companies: int           # boards polled this tick
    new: int                 # new postings surfaced


class RunPipelineIn(BaseModel):
    url: str
    run_id: str | None = None
    gate: bool = False
    match_only: bool = False
    make_cover_letter: bool = True
    target_pages: int = 1
    semantic_method: str = "lexical"


class TrackerMatchIn(BaseModel):
    entry_id: int


def _sources_for(selector: str) -> set[str] | None:
    """Resolve a tick selector to a source set. `all` -> None (every registered source)."""
    from resumaker.ingestion.scheduler import _FAST_SOURCES, _slow_sources
    if selector == "fast":
        return set(_FAST_SOURCES)
    if selector == "slow":
        return _slow_sources()
    return None  # "all"


@router.post("/ingest-tick", response_model=IngestTickOut)
def ingest_tick(body: IngestTickIn) -> IngestTickOut:
    """Run one watchlist poll over the selected source set (the Cloud Scheduler cron target).
    Idempotent - re-ingesting the same postings dedupes to zero new."""
    from resumaker.ingestion.scheduler import run_tick
    # Ingest only - the email digest is now its own Cloud Scheduler job (mailer-tick), decoupled
    # from ingestion cadence, so pausing/retiming email never affects discovery.
    results = run_tick(_sources_for(body.sources))
    new = sum(len(r.new_jobs) for r in results)
    return IngestTickOut(sources=body.sources, companies=len(results), new=new)


class MailerTickOut(BaseModel):
    emailed: int             # postings included in the digest this run (0 = none / quiet hours)


@router.post("/mailer-tick", response_model=MailerTickOut)
def mailer_tick() -> MailerTickOut:
    """Cloud Scheduler target (its own cadence = the Mailer 'frequency'): email the pending
    on-target backlog, honoring quiet hours + the max-postings cap. Backlog-wide, so anything
    deferred (quiet hours, or a slower cadence) goes out the next time this fires."""
    from resumaker.ingestion.notify import email_pending
    return MailerTickOut(emailed=email_pending())


@router.post("/tracker-match")
def tracker_match(body: TrackerMatchIn) -> dict:
    """Cloud Tasks target: run one tracked entry's match here on the worker (Claude CLI + real
    CPU + GCS publish) and update the entry in place. Runs inline; Tasks retries on non-2xx."""
    from resumaker.ingestion import tracker
    tracker.run_match_for(body.entry_id)
    return {"entry_id": body.entry_id, "ok": True}


@router.post("/run-pipeline", response_model=RunRecord)
def run_pipeline_endpoint(body: RunPipelineIn) -> RunRecord:
    """Execute ONE pipeline run synchronously and return its persisted record (the Cloud Tasks
    target). Runs inline on purpose: Cloud Tasks awaits the response and retries on non-2xx, so
    a crash surfaces as a 500 and gets redelivered. The orchestrator persists the `runs` row +
    artifacts, so status is durable regardless of which instance served the request."""
    run_id = body.run_id or uuid.uuid4().hex[:12]

    # Generation REUSES the match's persisted analysis instead of re-running it. The match already
    # scraped + structured the JD and ran keywords/gap, publishing them to report.json; re-doing
    # that is wasteful AND breaks captured/bot-walled jobs (a re-scrape hits e.g. LinkedIn's wall).
    # Load report.json and reconstruct the domain objects so run_pipeline skips scrape + structure +
    # keywords + gap - only tailor -> render -> fact-gate -> ats -> cover run. Anything missing or
    # unparseable falls through to `job=None` -> the plain scrape-by-url path (unchanged).
    job = keyword_set = gap = None
    with contextlib.suppress(Exception):
        raw = get_artifact_store().open(run_id, "report.json")
        data = json.loads(raw) if raw else {}
        if data.get("job"):
            job = JobPosting(**data["job"])                       # skips scrape + structure
            if data.get("keyword_set"):
                keyword_set = KeywordSet(**data["keyword_set"])   # skips keywords stage
            if data.get("gap"):
                gap = GapReport(**data["gap"])                    # skips gap stage

    res = run_pipeline(url=body.url, job=job, keyword_set=keyword_set, gap=gap, run_id=run_id,
                       gate=body.gate, match_only=body.match_only,
                       make_cover_letter=body.make_cover_letter, target_pages=body.target_pages,
                       semantic_method=body.semantic_method)
    # publish artifacts to durable storage (no-op on the local backend; GCS upload in cloud, so
    # they survive this ephemeral instance). Never fail the run if publishing hiccups.
    with contextlib.suppress(Exception):
        get_artifact_store().publish(run_id)

    rec = db.get_run(run_id)
    # Guarantee a TERMINAL status. The orchestrator's exception path returns `res.error` WITHOUT
    # indexing the run, so the row can be left at the pre-submit "running" status (or missing) and
    # the frontend's /progress poll would spin forever ("generating…"). Force it to "error" so
    # getProgress/getRun report done and the UI surfaces the failure instead of hanging.
    if res.error or rec is None or rec.status not in ("done", "matched", "gated_out"):
        db.set_run_status(run_id, "error", url=body.url)
        rec = db.get_run(run_id)
    if rec is not None:
        return rec
    # orchestrator persists on the happy path; synthesize a terminal record if it didn't.
    return RunRecord(id=run_id, url=body.url,
                     status="error" if res.error else "done", error=res.error or "")
