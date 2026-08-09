"""Discovery (RA.1): a deterministic, $0, LLM-free view over the ingested `jobs`.

The feed is *filtered*, never fit-scored against the resume - an empirical decision (a
resume/profile-based title fit score misranks genuine roles and degrades on an incomplete
profile). Real matching (fit/gap/sponsorship/keywords, LLM) happens only when a job is added
to the Tracker (RA.2). Filters here map to real columns: company, source, location, title
keyword, recency (`first_seen`), plus an optional `on_target` preference gate (target/avoid
role keywords). Pay is intentionally absent - ATS feeds only expose comp for disclosure
states and we don't yet capture it (follow-up: add a comp column + capture in ingest).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from resumaker.domain import JobRecord
from resumaker.ingestion.service import matches_preferences
from resumaker.persistence import db


@dataclass
class DiscoveryFilters:
    company: str | None = None
    source: str | None = None
    location: str | None = None       # substring, e.g. "boston" / "ny" / "remote"
    keyword: str | None = None        # title substring, e.g. "machine learning"
    since_days: int | None = None     # only postings first seen within N days
    on_target: bool = False           # apply the preference gate (target roles, no avoid)
    order: str = "recent"             # recent | company | title
    limit: int = 50
    offset: int = 0


@dataclass
class DiscoveryResult:
    total: int
    jobs: list[JobRecord]
    facets: dict


def discover(f: DiscoveryFilters) -> DiscoveryResult:
    """Return a filtered, paged slice of the feed + facet counts. When `on_target` is set we
    filter on the preference gate in Python (a keyword judgement, not a column), so we pull
    the filtered set and paginate after - fine at single-user scale (a few thousand rows)."""
    if f.on_target:
        rows = db.query_jobs(company=f.company, source=f.source, location_like=f.location,
                             title_like=f.keyword, since_days=f.since_days,
                             order=f.order, limit=100_000, offset=0)
        rows = [r for r in rows if matches_preferences(r.title)]
        total = len(rows)
        page = rows[f.offset:f.offset + f.limit]
        facets = {"companies": dict(Counter(r.company for r in rows).most_common()),
                  "sources": dict(Counter(r.source for r in rows).most_common())}
    else:
        total = db.count_jobs(company=f.company, source=f.source, location_like=f.location,
                              title_like=f.keyword, since_days=f.since_days)
        page = db.query_jobs(company=f.company, source=f.source, location_like=f.location,
                             title_like=f.keyword, since_days=f.since_days,
                             order=f.order, limit=f.limit, offset=f.offset)
        facets = db.job_facets(company=f.company, source=f.source, location_like=f.location,
                               title_like=f.keyword, since_days=f.since_days)
    return DiscoveryResult(total=total, jobs=page, facets=facets)
