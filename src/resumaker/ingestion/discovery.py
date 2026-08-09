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
from resumaker.ingestion.service import matches_preferences, title_level, us_states_of
from resumaker.persistence import db


@dataclass
class DiscoveryFilters:
    company: str | None = None
    source: str | None = None
    location: str | None = None       # substring, e.g. "boston" / "ny" / "remote"
    keyword: str | None = None        # title substring, e.g. "machine learning"
    since_days: int | None = None     # only postings first seen within N days
    on_target: bool = False           # apply the preference gate (target roles, no avoid)
    state: str | None = None          # US state code (e.g. "CA") or "OTHER" (unresolved/remote)
    level: str | None = None          # intern | junior | mid | senior | staff | manager
    order: str = "recent"             # recent | company | title
    limit: int = 50
    offset: int = 0


@dataclass
class DiscoveryResult:
    total: int
    jobs: list[JobRecord]
    facets: dict


def _match_state(job: JobRecord, state: str) -> bool:
    states = us_states_of(job.location)
    return not states if state == "OTHER" else state in states


def _apply(rows: list[JobRecord], *, company: str | None, source: str | None,
           on_target: bool, level: str | None, state: str | None) -> list[JobRecord]:
    """Apply the in-memory filters. `location`/`keyword`/`since_days` are already applied in
    SQL by the caller; company/source are done here (not SQL) so each facet can be computed
    with its OWN dimension excluded -> the dropdowns stay switchable after a selection."""
    out = rows
    if company:
        out = [r for r in out if r.company == company]
    if source:
        out = [r for r in out if r.source == source]
    if on_target:
        out = [r for r in out if matches_preferences(r.title)]
    if level:
        out = [r for r in out if title_level(r.title) == level]
    if state:
        out = [r for r in out if _match_state(r, state)]
    return out


def _state_counter(rows: list[JobRecord]) -> Counter:
    c: Counter = Counter()
    for r in rows:
        states = us_states_of(r.location)
        if states:
            c.update(states)
        else:
            c["OTHER"] += 1
    return c


def discover(f: DiscoveryFilters) -> DiscoveryResult:
    """Return a filtered, paged slice of the feed + facet counts. Column filters (company,
    source, location, keyword, recency) run in SQL; the preference gate, US-state and level
    filters are keyword/derived judgements applied in Python - so we pull the column-filtered
    set once and finish in memory (fine at single-user scale, a few thousand rows). Each facet
    is computed with its OWN filter excluded so the dropdowns still let you switch values."""
    base = db.query_jobs(location_like=f.location, title_like=f.keyword,
                         since_days=f.since_days, order=f.order, limit=100_000, offset=0)

    filtered = _apply(base, company=f.company, source=f.source, on_target=f.on_target,
                      level=f.level, state=f.state)
    total = len(filtered)
    page = filtered[f.offset:f.offset + f.limit]

    # Each facet is computed with ITS OWN dimension excluded, so selecting a value never
    # collapses that dropdown to a single option (you can always switch).
    for_co = _apply(base, company=None, source=f.source, on_target=f.on_target,
                    level=f.level, state=f.state)
    for_src = _apply(base, company=f.company, source=None, on_target=f.on_target,
                     level=f.level, state=f.state)
    for_states = _apply(base, company=f.company, source=f.source, on_target=f.on_target,
                        level=f.level, state=None)
    for_levels = _apply(base, company=f.company, source=f.source, on_target=f.on_target,
                        level=None, state=f.state)
    facets = {
        "companies": dict(Counter(r.company for r in for_co).most_common()),
        "sources": dict(Counter(r.source for r in for_src).most_common()),
        "states": dict(_state_counter(for_states).most_common()),
        "levels": dict(Counter(title_level(r.title) for r in for_levels).most_common()),
    }
    return DiscoveryResult(total=total, jobs=page, facets=facets)
