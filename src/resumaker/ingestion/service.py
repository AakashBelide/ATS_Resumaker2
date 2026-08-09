"""Watchlist ingestion service (RI.1/RI.2): list each watched company's boards, dedupe
postings into `jobs`, and surface what's new. Shared by the API, the CLI, and the
scheduler so the ingest path is defined once.

Dedupe: `db.upsert_job` keys on (source, external_id) and compares a `content_hash` over
the listing fields, so re-ingesting is idempotent and only genuinely new/changed postings
are flagged. A preference filter (target vs avoid role keywords) narrows what we notify on.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from resumaker.domain import Company, JobRecord
from resumaker.observability import metrics
from resumaker.observability.logging import get_logger
from resumaker.persistence import cache, db
from resumaker.providers.sources import get_source

_log = get_logger("resumaker.ingestion")


@dataclass
class IngestResult:
    company: str
    new: int = 0
    unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    new_jobs: list[JobRecord] = field(default_factory=list)


def _content_hash(stub) -> str:
    return cache.make_key(stub.title, stub.location, stub.updated_at)


def ingest_company(company: Company, *, preferred_only: bool = False) -> IngestResult:
    """List every board of `company`, dedupe into `jobs`, return counts + the new rows.
    `preferred_only` keeps only postings whose title matches job-search preferences."""
    res = IngestResult(company=company.name)
    for board in company.boards:
        try:
            stubs = get_source(board.source).list_postings(board.token, **board.extra)
        except Exception as e:  # noqa: BLE001 - one bad board must not sink the rest
            res.errors.append(f"{board.source}/{board.token}: {e}")
            continue
        for stub in stubs:
            if preferred_only and not matches_preferences(stub.title):
                continue
            rec = JobRecord(source=stub.source, external_id=stub.external_id, url=stub.url,
                            title=stub.title, company=company.name, location=stub.location,
                            content_hash=_content_hash(stub), posted_at=stub.updated_at)
            jid, changed = db.upsert_job(rec)
            if changed:
                res.new += 1
                rec.id = jid
                res.new_jobs.append(rec)
            else:
                res.unchanged += 1
    metrics.inc("resumaker_ingest_new_total", company=company.name, value=res.new)
    _log.info("ingested", extra={"company": company.name, "new": res.new,
                                 "unchanged": res.unchanged, "errors": len(res.errors)})
    return res


def ingest_all(*, preferred_only: bool = False) -> list[IngestResult]:
    return [ingest_company(c, preferred_only=preferred_only)
            for c in db.list_companies(active_only=True)]


def matches_preferences(title: str) -> bool:
    """True if the title looks on-target per preferences: contains a target-role keyword
    and no avoid keyword. Absent preferences -> everything passes (no filtering)."""
    from resumaker.enrichment import preferences
    prefs = preferences()
    t = (title or "").lower()
    targets = [k.lower() for k in prefs.get("target_roles", []) or []]
    avoids = [k.lower() for k in prefs.get("avoid_roles", []) or []]
    if avoids and any(a in t for a in avoids):
        return False
    if targets:
        return any(k in t for k in targets)
    return True
