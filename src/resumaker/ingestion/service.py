"""Watchlist ingestion service (RI.1/RI.2): list each watched company's boards, dedupe
postings into `jobs`, and surface what's new. Shared by the API, the CLI, and the
scheduler so the ingest path is defined once.

Dedupe: `db.upsert_job` keys on (source, external_id) and compares a `content_hash` over
the listing fields, so re-ingesting is idempotent and only genuinely new/changed postings
are flagged. A preference filter (target vs avoid role keywords) narrows what we notify on.
"""
from __future__ import annotations

import re
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


def ingest_company(company: Company, *, preferred_only: bool = False,
                   us_only: bool = True) -> IngestResult:
    """List every board of `company`, dedupe into `jobs`, return counts + the new rows.
    `preferred_only` keeps only titles matching job-search preferences; `us_only` (default)
    drops postings whose location is clearly outside the US (the candidate is US-based and
    relocates within the US, so global boards like Workday must be geo-filtered)."""
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
            if us_only and not is_us_location(stub.location):
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


_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
    "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
    "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
    "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
}
_US_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "ohio",
    "oklahoma", "oregon", "pennsylvania", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "wisconsin", "wyoming", "new york", "new jersey",
    "new mexico", "new hampshire", "north carolina", "north dakota", "south carolina",
    "south dakota", "rhode island", "west virginia",
}
_US_TERMS = ("united states", "u.s.a", "usa", " us", "us ", "u.s.", "remote us",
             "remote - us", "remote, us", "remote (us")
# Clearly-foreign markers: if present (and no explicit US state), treat as non-US.
_FOREIGN = {
    "india", "poland", "canada", "united kingdom", "uk", "ireland", "germany", "france",
    "spain", "italy", "netherlands", "sweden", "switzerland", "singapore", "australia",
    "china", "japan", "hong kong", "korea", "brazil", "mexico", "argentina", "israel",
    "philippines", "vietnam", "indonesia", "malaysia", "thailand", "romania", "portugal",
    "belgium", "denmark", "norway", "finland", "austria", "czech", "hungary", "greece",
    "turkey", "egypt", "south africa", "nigeria", "kenya", "uae", "dubai", "saudi",
    "new zealand", "colombia", "chile", "peru", "costa rica", "bangalore", "bengaluru",
    "hyderabad", "mumbai", "pune", "chennai", "gurgaon", "gurugram", "noida", "delhi",
    "london", "toronto", "vancouver", "montreal", "dublin", "krakow", "gdansk", "warsaw",
    "paris", "berlin", "munich", "amsterdam", "tokyo", "sydney", "bangkok", "manila",
}


def is_us_location(location: str) -> bool:
    """Heuristic: is this posting US-based? Empty/unknown counts as US (keep - the JD will
    clarify). An explicit US state name or US term wins; a 2-letter state abbr is only
    honored after a comma ('Boston, MA') to avoid matching prepositions like 'in'/'or';
    a foreign country/city (without a US state abbr) marks it out."""
    loc = (location or "").strip().lower()
    if not loc:
        return True
    if any(name in loc for name in _US_STATE_NAMES):
        return True
    if any(term in f" {loc} " for term in _US_TERMS):
        return True
    m = re.search(r",\s*([a-z]{2})\b", loc)     # 'City, ST' pattern only
    us_abbr = bool(m and m.group(1) in _US_STATES)
    # Foreign country/city (without a US state abbr) is out; US abbr or a bare city stays.
    is_foreign = any(f in loc for f in _FOREIGN) and not us_abbr
    return not is_foreign


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
