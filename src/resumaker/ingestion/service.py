"""Watchlist ingestion service (RI.1/RI.2): list each watched company's boards, dedupe
postings into `jobs`, and surface what's new. Shared by the API, the CLI, and the
scheduler so the ingest path is defined once.

Dedupe: `db.upsert_job` keys on (source, external_id) and compares a `content_hash` over
the listing fields, so re-ingesting is idempotent and only genuinely new/changed postings
are flagged. A preference filter (target vs avoid role keywords) narrows what we notify on.
"""
from __future__ import annotations

import concurrent.futures as cf
import random
import re
import time
from dataclasses import dataclass, field

from resumaker.config import get_settings
from resumaker.domain import BoardRef, Company, JobRecord
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


def _record_stubs(res: IngestResult, company: Company, stubs, *, tech_only: bool,
                  preferred_only: bool, us_only: bool) -> None:
    """Filter a board's postings and upsert the survivors into `jobs`, updating `res` counts +
    new rows. DB-only (no network): callers keep this on a single thread because the libSQL
    connection is shared process-wide and SQLite serializes writers anyway."""
    for stub in stubs:
        if tech_only and not is_tech_role(stub.title):
            continue
        if preferred_only and not matches_preferences(stub.title):
            continue
        if us_only and not is_us_location(stub.location):
            continue
        rec = JobRecord(source=stub.source, external_id=stub.external_id, url=stub.url,
                        title=stub.title, company=company.name, location=stub.location,
                        content_hash=_content_hash(stub), posted_at=stub.updated_at,
                        comp=stub.comp)
        jid, changed = db.upsert_job(rec)
        if changed:
            res.new += 1
            rec.id = jid
            res.new_jobs.append(rec)
        else:
            res.unchanged += 1


def _fetch_board(company: Company, board: BoardRef) -> tuple[Company, BoardRef, list, str]:
    """Network-only: list one board's postings. Returns (company, board, stubs, error) so a
    failed board is a value, not an exception - one bad board must not sink the sweep. Surfaces
    a blocked/misconfigured board (e.g. Microsoft TLS, Tesla 403) loudly, distinct from empty."""
    try:
        stubs = get_source(board.source).list_postings(board.token, **board.extra)
        return company, board, stubs, ""
    except Exception as e:  # noqa: BLE001 - one bad board must not sink the rest
        _log.error("board fetch failed", extra={"company": company.name,
                   "source": board.source, "token": board.token, "error": str(e)[:200]})
        return company, board, [], f"{board.source}/{board.token}: {e}"


def _fetch_source_group(items: list[tuple[Company, BoardRef]]) -> list:
    """Fetch every board in ONE source group serially, with polite jitter between calls. Boards
    on the same ATS source share a host (Greenhouse/Lever/Ashby are single-host; per-tenant
    sources like Workday still share the platform), so they must never fire concurrently."""
    out = []
    for i, (company, board) in enumerate(items):
        if i:
            time.sleep(random.uniform(0.5, 2.0))     # polite spacing within a host
        out.append(_fetch_board(company, board))
    return out


def ingest_company(company: Company, *, preferred_only: bool = False,
                   us_only: bool = True, tech_only: bool = True,
                   sources: set[str] | None = None) -> IngestResult:
    """List every board of `company`, dedupe into `jobs`, return counts + the new rows.
    Filters (all applied before dedupe): `tech_only` (default) keeps only engineering/tech
    titles - big enterprise boards are mostly non-tech; `us_only` (default) drops non-US
    postings; `preferred_only` further narrows to the owner's target roles. `sources`
    (optional) limits to boards on those ATSs (for per-cadence polling)."""
    res = IngestResult(company=company.name)
    for board in company.boards:
        if sources is not None and board.source not in sources:
            continue
        _, _, stubs, error = _fetch_board(company, board)
        if error:
            res.errors.append(error)
            continue
        if not stubs:
            # Fetch succeeded but yielded nothing: could be a real empty board, or a soft
            # failure (403/early-stop returning []). Flag it so it doesn't masquerade as 0.
            _log.warning("board returned no postings", extra={"company": company.name,
                         "source": board.source, "token": board.token})
        _record_stubs(res, company, stubs, tech_only=tech_only,
                      preferred_only=preferred_only, us_only=us_only)
    metrics.inc("resumaker_ingest_new_total", company=company.name, value=res.new)
    _log.info("ingested", extra={"company": company.name, "new": res.new,
                                 "unchanged": res.unchanged, "errors": len(res.errors)})
    return res


def ingest_all(*, preferred_only: bool = False, us_only: bool = True,
               tech_only: bool = True, sources: set[str] | None = None) -> list[IngestResult]:
    """Ingest every active company's selected boards, then dedupe into `jobs`.

    Fetch fan-out is grouped by ATS source (== host): up to `ingest_fetch_workers` groups run
    *concurrently* (independent hosts, no shared rate limit), while boards *within* a group stay
    serial + jittered (same host). Only the network fetch is parallel; DB writes are done back
    on this single thread as each group completes - the libSQL connection is shared process-wide
    (SQLite has one writer), and streaming the writes keeps a crashed tick's completed groups
    persisted. Re-ingest is idempotent (content-hash dedupe), so a partial tick self-heals next
    run. Net: a sweep costs ~the slowest host, not the sum of every board - without bursting one."""
    companies = db.list_companies(active_only=True)
    groups: dict[str, list[tuple[Company, BoardRef]]] = {}
    for c in companies:
        for b in c.boards:
            if sources is None or b.source in sources:
                groups.setdefault(b.source, []).append((c, b))

    results: dict[str, IngestResult] = {}

    def _write(fetched: list) -> None:                # single-threaded DB consumer
        for company, board, stubs, error in fetched:
            res = results.setdefault(company.name, IngestResult(company=company.name))
            if error:
                res.errors.append(error)
                continue
            if not stubs:
                _log.warning("board returned no postings", extra={"company": company.name,
                             "source": board.source, "token": board.token})
            _record_stubs(res, company, stubs, tech_only=tech_only,
                          preferred_only=preferred_only, us_only=us_only)

    if groups:
        workers = max(1, min(len(groups), get_settings().ingest_fetch_workers))
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_fetch_source_group, items) for items in groups.values()]
            for fut in cf.as_completed(futures):      # write each group the moment it finishes
                _write(fut.result())

    out: list[IngestResult] = []
    for c in companies:                               # keep watchlist order; emit metrics/logs
        res = results.get(c.name)
        if res is None:
            continue
        metrics.inc("resumaker_ingest_new_total", company=c.name, value=res.new)
        _log.info("ingested", extra={"company": c.name, "new": res.new,
                                     "unchanged": res.unchanged, "errors": len(res.errors)})
        if sources is None or res.new or res.unchanged or res.errors:
            out.append(res)
    return out


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


# Major US cities (tech hubs) -> state code. Purpose: rescue multi-city postings that name
# cities but NO state, e.g. McKinsey's "Atlanta, Boston" / "Boston, Chicago" (a comma with no
# US-state token would otherwise read as foreign). Deliberately EXCLUDES names that collide
# with well-known foreign cities (cambridge, birmingham, manchester, london, paris, ...) so
# the foreign check stays authoritative. Also feeds the Discovery state facet.
_US_CITY_TO_STATE = {
    "new york": "ny", "brooklyn": "ny", "san francisco": "ca", "los angeles": "ca",
    "san jose": "ca", "sunnyvale": "ca", "mountain view": "ca", "palo alto": "ca",
    "menlo park": "ca", "santa clara": "ca", "cupertino": "ca", "san diego": "ca",
    "san mateo": "ca", "oakland": "ca", "seattle": "wa", "bellevue": "wa", "redmond": "wa",
    "boston": "ma", "chicago": "il", "austin": "tx", "dallas": "tx", "houston": "tx",
    "plano": "tx", "atlanta": "ga", "denver": "co", "boulder": "co", "arlington": "va",
    "mclean": "va", "reston": "va", "pittsburgh": "pa", "philadelphia": "pa", "miami": "fl",
    "phoenix": "az", "tempe": "az", "minneapolis": "mn", "detroit": "mi", "charlotte": "nc",
    "raleigh": "nc", "durham": "nc", "nashville": "tn", "columbus": "oh", "salt lake city": "ut",
}


def is_us_location(location: str) -> bool:
    """Heuristic: is this posting US-based? Empty/unknown counts as US (keep - the JD will
    clarify). An explicit US state name or US term wins; then a 2-letter state abbr after a
    comma ('Boston, MA') is honored; then a known major US city ('Atlanta, Boston'); an
    explicit foreign country/city marker otherwise drops it.

    Special-case: India's country code 'In' collides with Indiana's 'IN'. When the string
    also names a foreign place, the ambiguous 'in' abbr is NOT allowed to rescue it - so
    'Bangalore, In' correctly reads as foreign, while 'Indianapolis, IN' (no foreign marker)
    stays US and 'Dublin, CA' (unambiguous CA) stays US."""
    loc = (location or "").strip().lower()
    if not loc:
        return True
    if any(name in loc for name in _US_STATE_NAMES):
        return True
    if any(term in f" {loc} " for term in _US_TERMS):
        return True
    foreign = any(f in loc for f in _FOREIGN)
    m = re.search(r",\s*([a-z]{2})\b", loc)     # 'City, ST' pattern only
    if m and m.group(1) in _US_STATES and not (foreign and m.group(1) == "in"):
        return True
    if foreign:                                 # explicit foreign country/city, no US signal
        return False
    if any(city in loc for city in _US_CITY_TO_STATE):   # 'Atlanta, Boston' (city, no state)
        return True
    # No US signal found. A structured "City, Region/Country" (has a comma) with no US
    # signal is almost certainly foreign (e.g. 'Bratislava, Bratislava') -> drop. A bare
    # single token ('Austin') or 'Remote' stays as ambiguous-keep.
    return "," not in loc


# state name -> 2-letter code, for deriving a state facet from the free-text location string
# (Discovery state dropdown). Reuses the abbr/name sets above; kept as an explicit map so we
# can go name -> code. Includes DC and (deliberately) 'west virginia' before 'virginia'.
_STATE_NAME_TO_CODE = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv", "ohio": "oh",
    "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa", "tennessee": "tn", "texas": "tx",
    "utah": "ut", "vermont": "vt", "washington": "wa", "wisconsin": "wi", "wyoming": "wy",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "west virginia": "wv", "virginia": "va", "district of columbia": "dc",
}


def us_states_of(location: str) -> list[str]:
    """Best-effort: which US state code(s) does this free-text location resolve to? Returns
    an uppercase, sorted, de-duplicated list (a posting may list several sites). Empty list =
    unresolved (remote / 'N Locations' / foreign / blank), which Discovery buckets as OTHER.
    Handles full state names, the 'City, ST' comma-abbr form, and the Workday 'US-CA-...'
    prefix. Deterministic, no LLM."""
    loc = (location or "").lower()
    if not loc:
        return []
    found: set[str] = set()
    for name, code in _STATE_NAME_TO_CODE.items():
        if name in loc:
            found.add(code.upper())
    for m in re.finditer(r",\s*([a-z]{2})\b", loc):     # 'San Jose, CA'
        if m.group(1) in _US_STATES:
            found.add(m.group(1).upper())
    for m in re.finditer(r"\bus[-\s]([a-z]{2})[-\s]", loc):     # 'US-CA-Menlo Park'
        if m.group(1) in _US_STATES:
            found.add(m.group(1).upper())
    for city, code in _US_CITY_TO_STATE.items():        # 'Atlanta, Boston' (city, no state)
        if city in loc:
            found.add(code.upper())
    return sorted(found)


# title -> coarse seniority level, for a deterministic (no-LLM) Discovery level filter. Word-
# boundary matched so 'intern' does not fire on 'international'. Precedence top to bottom.
_LEVEL_PATTERNS = [
    ("intern", re.compile(r"\bintern(ship)?\b|\bco[-\s]?op\b|\bapprentice")),
    ("manager", re.compile(r"\b(manager|mgr|director|head of|vp|vice president)\b")),
    ("staff", re.compile(r"\b(staff|principal|distinguished|fellow|architect)\b")),
    ("senior", re.compile(r"\b(senior|sr|lead)\b")),
    ("junior", re.compile(r"\b(junior|jr|entry[-\s]level|new[-\s]grad|graduate|early career)\b")),
]


def title_level(title: str) -> str:
    """Coarse seniority bucket from a job title: intern | junior | mid | senior | staff |
    manager. 'mid' is the residual (no level token). Deterministic, no LLM."""
    t = (title or "").lower()
    for level, pat in _LEVEL_PATTERNS:
        if pat.search(t):
            return level
    return "mid"


# Non-tech markers: if the title is clearly one of these, drop it even if it also contains
# a tech-ish token (e.g. "Sales Engineer", "Technical Recruiter"). Checked first.
_NONTECH = (
    "sales", "account executive", "account manager", "marketing", "recruit",
    "talent acquisition", "human resources", "hr ", "people partner", "legal", "counsel",
    "paralegal", "accountant", "auditor", " tax ", "payroll", "administrative",
    "executive assistant", "receptionist", "custodian", "janitor", "warehouse", "driver",
    "delivery", "cashier", "retail", "store associate", "store manager", "nurse",
    "clinical", "physician", "pharmacist", "therapist", "teacher", "barista", "cook",
    "server", "security guard", "facilities", "maintenance technician", "mechanic",
    "electrician", "plumber", "construction", "real estate", "procurement",
    "customer service", "call center", "teller", "branch manager", "underwriter",
    "communications", "public relations", "brand ", "copywriter", "social media",
    "supply chain", "logistics", "buyer", "merchandis",
)
# Tech markers: keep if any present (and no non-tech marker). Spaces guard short tokens.
_TECH_POS = (
    "engineer", "developer", "software", " sde", "sde ", "programmer", "data scien",
    "machine learning", " ml ", "ml/", "/ml", " ai ", "ai/", "/ai", "artificial intelligence",
    "deep learning", "nlp", "computer vision", "mlops", "devops", "site reliability", " sre",
    "platform", "infrastructure", "backend", "back end", "frontend", "front end",
    "full stack", "full-stack", "fullstack", "cloud", "architect", "data engineer",
    "analytics engineer", "data analyst", "research scientist", "applied scientist",
    "quant", "database", "distributed systems", "big data", "robotics", "embedded",
    "firmware", "security engineer", "cybersecurity", "systems engineer", "qa engineer",
    "test engineer", "solutions engineer", "ios ", "android ", "mobile engineer",
    "web developer", "api ", "sdet", "ml engineer", "ai engineer", "data science",
    "computer scientist", "technical program manager", "developer relations",
    # additions: clearly-technical roles the precision-first net was missing, plus
    # tech-QUALIFIED analyst/consultant (keeps 'Data/Analytics/Technology Consultant' and
    # 'Data Analyst' without letting bare 'Financial Analyst'/'Management Consultant' flood in)
    "research engineer", "research scientist", "applied scientist", "ml scientist",
    "statistician", "computational", "bioinformatics", "operations research", "python",
    "generative ai", "genai", "agentic", " llm ", "prompt engineer", "analytics",
    "business intelligence", "quantitative analyst", "data consultant",
    "analytics consultant", "technology consultant", "technical consultant",
    "ai consultant", "ml consultant", "cloud consultant", "digital consultant",
    "engineering consultant", "solution consultant", "data & analytics",
)


def is_tech_role(title: str) -> bool:
    """Keep engineering/tech/AI/ML/DS/DE titles; drop clearly non-technical ones. Precision-
    first (default-drop the ambiguous) - enterprise boards are mostly non-tech, so a focused
    watchlist wants high precision over recall."""
    t = f" {(title or '').lower()} "
    if any(m in t for m in _NONTECH):
        return False
    return any(m in t for m in _TECH_POS)


# On-target = a broad "is this in my field?" net. The stored preference labels ("Machine
# Learning Engineer", "Frontend Engineer (pure)") don't appear literally in real titles, so
# instead of substring-matching the labels we match a wide keyword net (engineer / developer /
# software / ai / ml / data / analyst / scientist / architect / python / ...), MINUS the avoid
# roles and a small pure-ops noise list. Word boundaries stop short tokens ('ai','ml','dev')
# firing inside unrelated words ('email','html','device'). This keeps SDE / Applied Scientist /
# ML / DS / DE / analyst / architect roles, while dropping 'Operations Technician' / 'IT
# Support'. Deterministic, no LLM.
_ONTARGET_RE = re.compile(
    r"\b("
    r"engineer|engineering|developer|software|programmer|architect\w*|sde|swe|"
    r"data|analyst|analytics|scientist|research|"
    r"machine\s*learning|artificial\s*intelligence|deep\s*learning|computer\s*vision|"
    r"nlp|llm|gen\s*ai|genai|generative|agentic|"
    r"ai|ml|mlops|devops|python|"
    r"cloud|platform|infrastructure|backend|back\s*end|full[-\s]?stack|"
    r"robotics|algorithm|quant\w*|statistic\w*|computational|bioinformatics"
    r")\b",
    re.IGNORECASE)
# Pure non-target roles that would otherwise slip the net via 'engineer'/'data'/etc.
_NON_TARGET_NOISE = (
    " operations technician", " operation technician", " ops technician",
    " it support", " help desk", " service desk", " desktop support",
    " field technician", " network technician", " data center technician",
    " support technician", " facilities ", " maintenance technician",
)
# Avoid label (parenthetical stripped) -> extra keyword variants to also block.
_AVOID_EXTRA = {
    "site reliability engineer": ["site reliability", " sre ", " sre,"],
    "frontend engineer": ["frontend engineer", "front end engineer", "front-end engineer"],
    "security engineer": ["security engineer"],
}


def title_matches(title: str, include: list[str] | None, exclude: list[str] | None) -> bool:
    """Ad-hoc title gate (case-insensitive substring): keep the title only if it contains at
    least ONE of the `include` words (when any are given) and NONE of the `exclude` words. Empty
    lists = no constraint. Shared by the Discovery title filter and the email digest filter, so a
    user can, e.g., require 'AI' and drop 'Java'/'Manager' titles."""
    t = (title or "").lower()
    inc = [w.lower() for w in (include or []) if w.strip()]
    exc = [w.lower() for w in (exclude or []) if w.strip()]
    if exc and any(w in t for w in exc):
        return False
    return not (inc and not any(w in t for w in inc))


def matches_preferences(title: str) -> bool:
    """True if the title is on-target: it's in the tech field (broad keyword net) and matches
    none of the avoid roles / pure-ops noise. See _ONTARGET_RE above for the rationale."""
    from resumaker.enrichment import preferences
    prefs = preferences()
    t = f" {(title or '').lower()} "

    if any(n in t for n in _NON_TARGET_NOISE):
        return False
    for a in prefs.get("avoid_roles", []) or []:
        base = re.sub(r"\(.*?\)", "", a).strip().lower()     # drop '(pure)' / '(pure infra)'
        if base and (base in t or any(x in t for x in _AVOID_EXTRA.get(base, []))):
            return False
    return bool(_ONTARGET_RE.search(title or ""))
