"""Watchlist scheduler (RI.3): poll every watched company on a cadence, dedupe, and
notify on new preference-matching postings. Never runs the pipeline or applies - it
surfaces work for the human to trigger.

Two cadences, because the ATSs differ in bot-tolerance:
  - the clean public JSON boards (Greenhouse/Lever/Ashby) poll often (hourly by default);
  - Workday (Akamai-fronted, throttles) polls gently (daily by default).
Uses APScheduler's in-memory jobstore: the schedule is defined from config and re-
registered on every boot, so it "survives restart" without a persistent store (and
without SQLAlchemy). APScheduler is lazy-imported (it lives in the `api` extra).
"""
from __future__ import annotations

from resumaker.config import get_settings
from resumaker.ingestion.notify import notify_new
from resumaker.ingestion.service import IngestResult, ingest_all
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.ingestion.scheduler")

_FAST_SOURCES = {"greenhouse", "lever", "ashby"}
_SLOW_SOURCES = {"workday"}


def run_tick(sources: set[str] | None = None) -> list[IngestResult]:
    """One poll over the given ATS sources (all if None): ingest -> tech+US filter -> dedupe
    -> notify. Uses the broad tech-role gate (not the narrower target-role preference) so we
    catch all of SWE/AI/ML/DS/DE, not just the exact preferred titles."""
    results = ingest_all(tech_only=True, us_only=True, sources=sources)
    new_jobs = [j for r in results for j in r.new_jobs]
    notify_new(new_jobs)
    _log.info("watchlist tick", extra={"sources": sorted(sources) if sources else "all",
                                       "companies": len(results), "new": len(new_jobs)})
    return results


def build_scheduler():
    """A started BackgroundScheduler with two jobs: fast boards + gentle Workday."""
    from apscheduler.schedulers.background import BackgroundScheduler
    s = get_settings()
    sched = BackgroundScheduler()
    sched.add_job(lambda: run_tick(_FAST_SOURCES), "interval",
                  minutes=s.scheduler_interval_minutes, id="boards_fast",
                  replace_existing=True)
    sched.add_job(lambda: run_tick(_SLOW_SOURCES), "interval",
                  minutes=s.scheduler_workday_interval_minutes, id="workday_slow",
                  replace_existing=True)
    return sched
