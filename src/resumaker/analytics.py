"""Analytics (RA.4 Dashboard + RA.5 Metrics): deterministic, $0 read-only aggregates over
the derived SQLite tables + the LLM usage log. No LLM. Powers the CLI `dashboard`/`metrics`
and the API `/v1/dashboard` / `/v1/metrics`; the frontend renders these directly.
"""
from __future__ import annotations

from resumaker.observability import cost
from resumaker.persistence import db


def dashboard_stats(days: int = 14, top: int = 15) -> dict:
    """Feed + funnel snapshot: watchlist size, jobs by company/source, the new-listings
    trend, the application funnel, and pipeline-run outcomes."""
    facets = db.job_facets()
    companies = dict(sorted(facets["companies"].items(), key=lambda x: -x[1])[:top])
    return {
        "watchlist": {
            "companies": len(db.list_companies(active_only=False)),
            "jobs": db.count_jobs(),
            "tracked": len(db.list_tracker()),
        },
        "jobs_by_company": companies,
        "jobs_by_source": facets["sources"],
        "new_listings_daily": db.jobs_daily(days),
        "tracker_funnel": db.tracker_funnel(),
        "runs": db.run_stats(),
    }


def metrics_overview() -> dict:
    """Model calls / cost / usage (RA.5). `cost.summary()` already aggregates calls, tokens
    and spend per provider (+ the Gemini budget headroom); we pair it with run outcomes."""
    return {"cost": cost.summary(), "runs": db.run_stats()}
