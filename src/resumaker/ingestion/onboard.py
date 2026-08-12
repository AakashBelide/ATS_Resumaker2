"""Auto-onboard a company onto the watchlist from just its name (RI).

Two-tier discovery (per owner's choice):
  1. slug-probe: derive candidate slugs from the name and hit the Greenhouse / Lever /
     Ashby public board APIs; a 200 with postings = found.
  2. careers-page parse: fetch a careers URL (provided, or guessed from the name) and
     extract the ATS board from any greenhouse/lever/ashby/myworkdayjobs link on it -
     this is how Workday tenants get resolved.

Anything still unresolved is reported as `manual` (the owner can pass an explicit
`careers_url` or board token). Fetching uses a pluggable layer (httpx -> Playwright),
so a stealth backend (Scrapling/Firecrawl) can slot in behind `fetch_html` later.
"""
from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx

from resumaker.domain import BoardRef
from resumaker.observability.logging import get_logger
from resumaker.providers.sources import get_source

_log = get_logger("resumaker.ingestion.onboard")
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_STOP = {"the", "inc", "llc", "corp", "co", "company", "group", "and", "&"}


@dataclass
class OnboardResult:
    name: str
    boards: list[BoardRef] = field(default_factory=list)
    method: str = ""              # slug-probe | careers-page | none
    tried: list[str] = field(default_factory=list)
    resolved: bool = False
    note: str = ""


# ------------------------------------------------------------------ slugs
def slug_candidates(name: str) -> list[str]:
    """Distinct board-slug guesses from a company name, most-likely first. We deliberately
    do NOT emit the bare first word (e.g. 'capital' from 'Capital One') - short partials
    match unrelated boards. Only the full concatenation + hyphenation per name part."""
    parts = re.split(r"[\/,]| - | and ", name)        # split "JPMC - Chase", "X/Y"
    cands: list[str] = []
    for part in [name, *parts]:
        words = [w for w in re.sub(r"[^a-z0-9\s]", " ", part.lower()).split()
                 if w and w not in _STOP]
        if not words:
            continue
        cands.append("".join(words))                  # statestreet
        if len(words) > 1:
            cands.append("-".join(words))             # state-street
    # de-dupe (order-preserving) + drop implausibly short slugs
    return [c for c in dict.fromkeys(cands) if len(c) >= 4]


# ------------------------------------------------------------------ tier 1: probe
def _name_matches(query: str, board_name: str) -> bool:
    """Loose match between the queried company and a board's official name."""
    from rapidfuzz import fuzz
    q = re.sub(r"[^a-z0-9]", "", query.lower())
    b = re.sub(r"[^a-z0-9]", "", (board_name or "").lower())
    if not b:
        return False
    return q in b or b in q or fuzz.partial_ratio(q, b) >= 85


def _greenhouse_board_name(token: str) -> str:
    try:
        r = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{token}",
                      headers={"User-Agent": _UA}, timeout=15, follow_redirects=True)
        return r.json().get("name", "") if r.status_code == 200 else ""
    except Exception:  # noqa: BLE001
        return ""


def _probe(name: str, source: str, slug: str) -> bool:
    """A hit requires postings AND (for Greenhouse) that the board's official name matches
    the queried company - this rejects squatter/namesake boards (e.g. a stray 'linkedin')."""
    try:
        if len(get_source(source).list_postings(slug)) == 0:
            return False
    except Exception:  # noqa: BLE001 - not this board / not this company
        return False
    if source == "greenhouse":
        return _name_matches(name, _greenhouse_board_name(slug))
    return True


def probe_boards(name: str) -> BoardRef | None:
    for slug in slug_candidates(name):
        for source in ("greenhouse", "lever", "ashby"):
            if _probe(name, source, slug):
                _log.info("slug-probe hit",
                          extra={"name": name, "source": source, "slug": slug})
                return BoardRef(source=source, token=slug)
    return None


# ------------------------------------------------------------------ tier 2: careers page
def fetch_html(url: str) -> str:
    """Fetch a page's HTML. Plain httpx first; Playwright fallback for JS/bot pages.
    A stealth backend (Scrapling/Firecrawl) can replace this behind the same signature."""
    try:
        r = httpx.get(url, headers={"User-Agent": _UA}, timeout=20, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:  # noqa: BLE001
        pass
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page(user_agent=_UA)
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                pg.wait_for_timeout(1200)
                return pg.content()
            finally:
                b.close()
    except Exception:  # noqa: BLE001
        return ""


def board_from_html(html: str) -> BoardRef | None:
    """Extract the first supported ATS board reference from careers-page HTML."""
    m = re.search(r"(?:job-boards|boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)", html)
    if m:
        return BoardRef(source="greenhouse", token=m.group(1))
    m = re.search(r"jobs\.lever\.co/([\w-]+)", html)
    if m:
        return BoardRef(source="lever", token=m.group(1))
    m = re.search(r"jobs\.ashbyhq\.com/([\w-]+)", html)
    if m:
        return BoardRef(source="ashby", token=m.group(1))
    m = re.search(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[\w-]+/)?([\w-]+)", html)
    if m:
        tenant, wd, site = m.group(1), m.group(2), m.group(3)
        return BoardRef(source="workday", token=tenant,
                        extra={"host": f"{tenant}.{wd}.myworkdayjobs.com", "site": site})
    return None


def discover_algolia(url: str) -> BoardRef | None:
    """Recover an Algolia-backed careers board (app id + search-only key + index).

    Sites like Rippling render jobs via Algolia InstantSearch; the credentials exist ONLY at
    runtime (not in the HTML/JS we can curl), so we drive a headless browser, watch for the
    page's own Algolia search request, and read the app id + key off it (they ride as query
    params or headers). The index comes from the request body or the page's `algoliaIndexName`.
    Returns a `BoardRef(source="algolia", ...)` the AlgoliaSource adapter can list."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - Playwright not installed
        return None
    found: dict[str, str] = {}

    def _on_request(req) -> None:  # noqa: ANN001
        u = req.url
        if found or ("algolia.net" not in u and "algolianet.com" not in u):
            return
        q = parse_qs(urlsplit(u).query)
        app = (q.get("x-algolia-application-id") or [""])[0] or req.headers.get("x-algolia-application-id", "")
        key = (q.get("x-algolia-api-key") or [""])[0] or req.headers.get("x-algolia-api-key", "")
        if not (app and key):
            return
        m = (re.search(r'"indexName"\s*:\s*"([^"]+)"', req.post_data or "") if req.post_data else None) \
            or re.search(r"/1/indexes/([^/*]+)/query", u)
        idx = m.group(1) if m else ""
        found.update({"app": app, "key": key, "index": idx, "host": urlsplit(u).hostname or ""})

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page(user_agent=_UA)
            pg.on("request", _on_request)
            # `domcontentloaded` (not `networkidle`): analytics-heavy careers pages never go idle,
            # and the InstantSearch query we need fires shortly after load — a fixed settle wait is
            # enough. A goto timeout must NOT discard an already-captured request.
            with contextlib.suppress(Exception):
                pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                pg.wait_for_timeout(5000)
                if found and not found.get("index"):  # last-resort: static config on the page
                    m = re.search(r'"algoliaIndexName"\s*:\s*"([^"]+)"', pg.content())
                    if m:
                        found["index"] = m.group(1)
            except Exception:  # noqa: BLE001
                pass
            b.close()
    except Exception:  # noqa: BLE001 - Playwright/Chromium launch failure
        return None

    if found.get("app") and found.get("key") and found.get("index"):
        return BoardRef(source="algolia", token=found["app"],
                        extra={"index": found["index"], "api_key": found["key"],
                               "host": found["host"], "careers_url": url})
    return None


def discover_from_careers(name: str, careers_url: str) -> BoardRef | None:
    """Resolve a board from a careers URL. First parse the URL string itself (a direct
    `*.myworkdayjobs.com` / greenhouse / lever / ashby link resolves with no fetch - and
    Workday sites are JS SPAs that fetch empty anyway); else fetch + parse the page; else, for
    custom Algolia-search careers pages, capture the runtime Algolia credentials."""
    board = board_from_html(careers_url) or board_from_html(fetch_html(careers_url))
    if board is None:
        board = discover_algolia(careers_url)
    if board:
        _log.info("careers-page hit",
                  extra={"name": name, "url": careers_url, "source": board.source})
    return board


# ------------------------------------------------------------------ entrypoint
def resolve(name: str, *, careers_url: str | None = None) -> OnboardResult:
    """Resolve a company to a board ref: fast slug-probe first, then - only if a careers
    URL is supplied - parse it. Blind domain-guessing is intentionally omitted (slow +
    unreliable); the owner supplies a careers URL for anything slug-probe misses."""
    res = OnboardResult(name=name)
    board = probe_boards(name)
    if board:
        res.boards, res.method, res.resolved = [board], "slug-probe", True
        return res
    if careers_url:
        res.tried = [careers_url]
        board = discover_from_careers(name, careers_url)
        if board:
            res.boards, res.method, res.resolved = [board], "careers-page", True
            return res
    res.method = "none"
    res.note = ("unresolved - provide a careers_url (helps resolve Workday/custom) or a "
                "board token; company may use an unsupported ATS")
    return res
