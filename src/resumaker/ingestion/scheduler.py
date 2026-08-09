"""Watchlist scheduler (RI.3): poll every watched company on a cadence, dedupe, and
notify on new preference-matching postings. Never runs the pipeline or applies - it
surfaces work for the human to trigger.

Uses APScheduler's in-memory jobstore: the schedule is a single fixed-interval job defined
from config and re-registered on every boot, so it "survives restart" without a persistent
store (and without pulling in SQLAlchemy). APScheduler is lazy-imported (it lives in the
`api` extra), so importing this module in a core-only install is safe.
"""
from __future__ import annotations

from resumaker.config import get_settings
from resumaker.ingestion.notify import notify_new
from resumaker.ingestion.service import IngestResult, ingest_all
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.ingestion.scheduler")


def run_tick() -> list[IngestResult]:
    """One poll: ingest all watched companies (preference-filtered) and notify on new."""
    results = ingest_all(preferred_only=True)
    new_jobs = [j for r in results for j in r.new_jobs]
    notify_new(new_jobs)
    _log.info("watchlist tick", extra={"companies": len(results),
                                       "new": len(new_jobs)})
    return results


def build_scheduler():
    """A started BackgroundScheduler running run_tick on the configured interval."""
    from apscheduler.schedulers.background import BackgroundScheduler
    s = get_settings()
    sched = BackgroundScheduler()
    sched.add_job(run_tick, "interval", minutes=s.scheduler_interval_minutes,
                  id="watchlist_ingest", replace_existing=True)
    return sched
