"""Workday board-listing adapter via the CxS jobs endpoint (JSON, paginated).

Workday sits behind Akamai (TLS/JA3 fingerprinting), so we impersonate Chrome with
curl_cffi. A board needs the tenant host + site path, passed via the BoardRef `extra`:
    BoardRef(source="workday", token="<tenant>",
             extra={"host": "<tenant>.wd1.myworkdayjobs.com", "site": "External"})
The emitted URL matches the single-JD Workday scraper so the full JD is fetched cleanly.

Politeness (Workday throttles rapid sequential pages): we jitter-sleep between pages and
back off on 429/403 before giving up, so scheduled daily polling stays under the radar.

Reaching tech roles: Workday's default (`searchText=""`) ordering surfaces retail/branch/
pharmacy roles first, so on big enterprise boards (Walmart, Fidelity, TD, ...) SWE/ML/data
roles are buried thousands deep and a shallow fetch never reaches them. Instead of pulling
the entire catalog we run a handful of tech-targeted `searchText` queries (relevance-ordered
by Workday) and dedupe across them - this makes the relevant intersection reachable cheaply.
A throttle/backoff give-up ends only the current query, not the whole board, so a transient
block no longer zeroes the board.
"""
from __future__ import annotations

import random
import time

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub

_log = get_logger("resumaker.sources.workday")
_MAX_PAGES = 20          # per query; relevance-ordered, so relevant roles land in this window
_PAGE = 20
_PAGE_PAUSE = (0.6, 1.6)  # jitter (s) between pages - avoids the ~page-3 throttle
# Tech-targeted queries: broad enough to cover SWE/ML/DS/DE across enterprise Workday boards,
# narrow enough to keep the fetch light. Downstream is_tech_role/is_us_location still filter.
_SEARCH_TERMS = ("software engineer", "machine learning", "data", "developer")


class WorkdaySource:
    source = "workday"

    def list_postings(self, token: str, *, host: str = "", site: str = "",
                      **kwargs: str) -> list[PostingStub]:
        if not host or not site:
            raise ValueError("workday board needs extra={'host':..., 'site':...}")
        from curl_cffi import requests as cffi
        cxs = f"https://{host}/wday/cxs/{token}/{site}/jobs"
        out: list[PostingStub] = []
        seen: set[str] = set()
        for term in _SEARCH_TERMS:
            self._collect(cffi, cxs, host, site, term, out, seen)
        return out

    def _collect(self, cffi, cxs: str, host: str, site: str, term: str,
                 out: list[PostingStub], seen: set[str]) -> None:
        """Paginate one tech-targeted query, respecting `total`, appending de-duped stubs."""
        offset = 0
        for _ in range(_MAX_PAGES):
            body = self._post(cffi, cxs, offset, term)
            if body is None:                        # gave up after backoff - end this query
                break
            postings = body.get("jobPostings", []) or []
            for jp in postings:
                ext = jp.get("externalPath", "")
                req_id = (jp.get("bulletFields") or [""])[0]
                key = str(req_id or ext)
                if not key or key in seen:          # dedupe across the search terms
                    continue
                seen.add(key)
                out.append(PostingStub(
                    source=self.source,
                    external_id=key,
                    url=f"https://{host}/{site}{ext}",
                    title=jp.get("title", ""),
                    location=jp.get("locationsText", ""),
                    updated_at=str(jp.get("postedOn", "")),   # relative, e.g. "Posted 3 Days Ago"
                ))
            offset += _PAGE
            if not postings or offset >= int(body.get("total", 0) or 0):
                break
            time.sleep(random.uniform(*_PAGE_PAUSE))          # polite spacing between pages

    @staticmethod
    def _post(cffi, cxs: str, offset: int, search_text: str) -> dict | None:
        """POST one page; retry on 429/403 with backoff. Returns the body or None if blocked."""
        payload = {"appliedFacets": {}, "limit": _PAGE, "offset": offset,
                   "searchText": search_text}
        for attempt in range(4):
            try:
                r = cffi.post(cxs, impersonate="chrome", timeout=30, json=payload)
            except Exception as e:  # noqa: BLE001 - network blip
                _log.warning("workday post error", extra={"cxs": cxs, "error": str(e)[:120]})
                return None
            if r.status_code == 200:
                return r.json() or {}
            if r.status_code in (429, 403):                   # throttled - back off and retry
                retry_after = r.headers.get("Retry-After")    # honor server's hint if given
                delay = (float(retry_after) if (retry_after or "").isdigit()
                         else 2.0 * (attempt + 1) + random.uniform(0, 1))
                time.sleep(delay)
                continue
            return None                                       # 404/5xx etc. - stop this query
        _log.warning("workday throttled, giving up",
                     extra={"cxs": cxs, "offset": offset, "searchText": search_text})
        return None
