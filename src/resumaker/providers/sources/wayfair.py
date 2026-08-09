"""Wayfair careers adapter (internal job_search_data XHR). Single-company (token ignored).

Wayfair's careers UI is PerimeterX/HUMAN-protected: a plain httpx POST to the jobs XHR gets a
429 challenge. But the gate is TLS/fingerprint-based, so curl_cffi Chrome-impersonation clears
it - we (1) GET the careers page in a session to warm the PX/session cookies, then (2) POST
the `job_search_data` XHR, which returns the ENTIRE US catalog in one call (`countryIds:[1]`).
No pagination. The Avature `applyLink` is provided per posting. A cold datacenter run works
via curl_cffi, but a residential IP is the safest egress. The response PARSER is fixture
unit-tested. US is filtered server-side and re-checked client-side.
"""
from __future__ import annotations

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub

_log = get_logger("resumaker.sources.wayfair")
_PAGE_URL = "https://www.wayfair.com/careers/jobs/?countryIds=1"
_XHR_URL = "https://www.wayfair.com/a/careers/careers/job_search_data"
_US = 1  # countryId 1 == United States (mapping confirmed live: CA=3, UK=4, Remote=7, India=10)


def _search_body() -> dict:
    return {"categoryIds": [], "teamIds": [], "locationIds": [], "countryIds": [_US],
            "teamCategoryIds": [], "stateIds": [], "selectedJobTypeIds": [], "keywords": ""}


def parse_response(body: dict) -> list[PostingStub]:
    """Parse a job_search_data response into stubs. Defensive to shape drift."""
    jobs = (body or {}).get("jobListData") or []
    out: list[PostingStub] = []
    for j in jobs:
        loc = j.get("location") or {}
        loc_str = loc.get("name") or ", ".join(
            x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x)
        out.append(PostingStub(
            source="wayfair", external_id=str(j.get("id", "") or j.get("eid", "")),
            url=j.get("applyLink", "") or j.get("structuredDataApplyLink", ""),
            title=j.get("title", ""), location=str(loc_str),
            updated_at=str(j.get("lastUpdatedDate", "") or j.get("createdDate", ""))))
    return out


class WayfairSource:
    source = "wayfair"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        from curl_cffi import requests as cffi
        headers = {"content-type": "application/json", "accept": "application/json",
                   "x-requested-with": "XMLHttpRequest",
                   "referer": _PAGE_URL, "origin": "https://www.wayfair.com"}
        try:
            s = cffi.Session()
            warm = s.get(_PAGE_URL, impersonate="chrome", timeout=30)   # mint PX/session cookies
            if warm.status_code != 200:
                _log.warning("wayfair warmup non-200 (PerimeterX)",
                             extra={"status": warm.status_code})
                return []
            r = s.post(_XHR_URL, impersonate="chrome", timeout=45,
                       json=_search_body(), headers=headers)
        except Exception as e:  # noqa: BLE001 - network blip / TLS block
            _log.warning("wayfair error", extra={"error": str(e)[:120]})
            return []
        if r.status_code != 200:
            _log.warning("wayfair xhr non-200 (PerimeterX)", extra={"status": r.status_code})
            return []
        return parse_response(r.json() or {})
