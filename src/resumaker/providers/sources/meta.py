"""Meta / Facebook careers adapter (metacareers.com GraphQL). Single-company.

Meta serves its listings from a persisted GraphQL query (`CareersJobSearchResultsDataQuery`)
whose `doc_id` ROTATES on every frontend deploy and lives in a JS bundle (not the page HTML),
and the POST needs an `lsd` CSRF token minted by the page. So the handshake, in one client:
  1. GET the jobs page  -> scrape `lsd` + the `fbcdn.net` JS bundle URLs;
  2. walk the bundles    -> extract the current `doc_id` from the Relay operation module;
  3. POST /graphql       -> the query with full browser headers + `x-fb-lsd`.
One call returns the entire list (`all_jobs`), so no pagination. Facebook's edge bot-defense
is aggressive from datacenter IPs (a bare request 400s; rapid calls get the IP blocked), so
this is verified from a residential network and polled gently (daily tier). The pure parsing
steps are fixture unit-tested. US filtering is client-side on `locations` (no working server
country param); the service's `is_us_location` gate handles it.
"""
from __future__ import annotations

import json
import re

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub

_log = get_logger("resumaker.sources.meta")
_PAGE_URL = "https://www.metacareers.com/jobs/"
_GQL_URL = "https://www.metacareers.com/graphql"
_FRIENDLY = "CareersJobSearchResultsDataQuery"
_LSD_RE = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"\}')
_BUNDLE_RE = re.compile(r'https://[a-z.\-]*fbcdn\.net/rsrc\.php/[^"\'\s]+\.js[^"\'\s]*')
# The doc_id is defined as a Relay operation module in a JS bundle:
#   __d("CareersJobSearchResultsDataQuery_..RelayOperation",[],(function(...){a.exports="123"})
_DOCID_RE = re.compile(_FRIENDLY + r'[^"]*RelayOperation",\[\],\(function\([^)]*\)\{'
                       r'[a-z]\.exports="(\d+)"')
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="120", "Not;A=Brand";v="99"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document", "sec-fetch-mode": "navigate", "sec-fetch-site": "none",
    "upgrade-insecure-requests": "1",
}


def scrape_lsd(html: str) -> str:
    m = _LSD_RE.search(html or "")
    return m.group(1) if m else ""


def find_bundle_urls(html: str) -> list[str]:
    """Unique fbcdn JS bundle URLs referenced by the page, in first-seen order."""
    seen: dict[str, None] = {}
    for u in _BUNDLE_RE.findall(html or ""):
        seen.setdefault(u, None)
    return list(seen)


def extract_doc_id(js: str) -> str:
    m = _DOCID_RE.search(js or "")
    return m.group(1) if m else ""


def parse_response(body: dict) -> list[PostingStub]:
    """Parse the query response into stubs. Path: data.job_search_with_featured_jobs
    .{all_jobs,featured_jobs}; falls back to the older flat `job_search`. Defensive."""
    data = (body or {}).get("data") or {}
    jsw = data.get("job_search_with_featured_jobs") or {}
    jobs = (jsw.get("all_jobs") or []) + (jsw.get("featured_jobs") or [])
    if not jobs:
        jobs = data.get("job_search") or []
    out: list[PostingStub] = []
    for j in jobs:
        jid = str(j.get("id", ""))
        if not jid:
            continue
        locs = j.get("locations") or []
        loc = ", ".join(str(x) for x in locs[:2]) if isinstance(locs, list) else str(locs)
        out.append(PostingStub(
            source="meta", external_id=jid,
            url=f"https://www.metacareers.com/jobs/{jid}/",
            title=j.get("title", ""), location=loc,
            updated_at=""))                            # not exposed by this query variant
    return out


def _resolve_doc_id(client, html: str) -> str:
    """Walk the page's JS bundles until one yields the current doc_id (rotates per deploy)."""
    for url in find_bundle_urls(html)[:60]:
        try:
            js = client.get(url)
        except Exception:  # noqa: BLE001 - skip a flaky bundle
            continue
        if js.status_code == 200 and (doc := extract_doc_id(js.text)):
            return doc
    return ""


def _build_form(lsd: str, doc_id: str) -> dict:
    variables = {
        "hasLoggedInUser": False, "isLoggedIn": False, "loggedOutUUID": None,
        "locale": "en_US", "fallback_locale": "en_US", "referrer": None,
        "search_input": {"q": None},
        "session_id": None, "skip_exchange": True, "is_match_checker": False,
        "hasConsideration": False, "consideration_id": None, "viewasUserID": None}
    return {"av": "0", "__user": "0", "__a": "1", "lsd": lsd,
            "fb_api_caller_class": "RelayModern", "fb_api_req_friendly_name": _FRIENDLY,
            "doc_id": doc_id, "server_timestamps": "true",
            "variables": json.dumps(variables)}


class MetaSource:
    source = "meta"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        import httpx
        with httpx.Client(headers=_BROWSER_HEADERS, timeout=30, follow_redirects=True) as client:
            page = client.get(_PAGE_URL)
            if page.status_code != 200:
                _log.warning("meta page non-200", extra={"status": page.status_code})
                return []
            lsd = scrape_lsd(page.text)
            doc_id = _resolve_doc_id(client, page.text)
            if not lsd or not doc_id:                  # handshake failed (bundle/markup drift)
                _log.warning("meta handshake incomplete",
                             extra={"lsd": bool(lsd), "doc_id": bool(doc_id)})
                return []
            r = client.post(_GQL_URL, data=_build_form(lsd, doc_id), headers={
                "x-fb-lsd": lsd, "x-fb-friendly-name": _FRIENDLY,
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://www.metacareers.com", "referer": _PAGE_URL,
                "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors"})
            if r.status_code != 200:
                _log.warning("meta graphql non-200", extra={"status": r.status_code})
                return []
            try:
                body = r.json()
            except json.JSONDecodeError:               # FB may prefix anti-hijack junk
                body = json.loads(r.text.split("\n", 1)[-1])
        return parse_response(body)
