"""Paradox "careersites" adapter (`/api/get-jobs`). Covers FedEx and other Paradox-hosted
career sites.

    BoardRef(source="paradox", token="fedex", extra={"host": "careers.fedex.com"})

Two-step handshake: the search API sits behind an Akamai-style WAF that 403s a cold POST, so
we first GET `/jobs` in a shared client to mint the `ct` session cookie, then POST
`/api/get-jobs` with that cookie + browser-like headers (verified to return 200 from a plain
datacenter IP once the cookie is present). Search params ride in the query string (nested
`filter[...]` facets); the POST body is a small constant. The response PARSER is fixture
unit-tested; the live handshake is verified from the user's network. US filtered server-side
via `filter[country][0]=United States` and again client-side.
"""
from __future__ import annotations

from urllib.parse import urlencode

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub

_log = get_logger("resumaker.sources.paradox")
_PAGE = 50
_MAX_PAGES = 20
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_DATE_KEYS = {"cf_effective_date", "cf_workday_earliest_hire_date"}


def _posted_date(job: dict) -> str:
    """FedEx has no top-level date; it lives in customFields keyed by cfKey."""
    for cf in job.get("customFields") or []:
        if cf.get("cfKey") in _DATE_KEYS and cf.get("value"):
            return str(cf["value"])
    return ""


def _location(job: dict) -> str:
    locs = job.get("locations") or []
    if not locs:
        return "Remote" if job.get("isRemote") else ""
    first = locs[0] or {}
    return first.get("locationName") or ", ".join(
        x for x in (first.get("city"), first.get("stateAbbr"), first.get("countryAbbr"))
        if x)


def parse_response(body: dict) -> tuple[list[PostingStub], int]:
    """Parse a get-jobs response into (stubs, total). Defensive to shape drift."""
    body = body or {}
    jobs = body.get("jobs") or []
    total = int(body.get("totalJob") or 0)
    out: list[PostingStub] = []
    for j in jobs:
        out.append(PostingStub(
            source="paradox",
            external_id=str(j.get("uniqueID", "") or j.get("reference", "")),
            url=j.get("applyURL", "") or j.get("originalURL", ""),
            title=j.get("title", ""),
            location=_location(j),
            updated_at=_posted_date(j),
        ))
    return out, total


class ParadoxSource:
    source = "paradox"

    def list_postings(self, token: str, *, host: str = "", **kwargs: str) -> list[PostingStub]:
        if not host:
            raise ValueError("paradox board needs extra={'host': ...}")
        import httpx
        base = f"https://{host}"
        headers = {"User-Agent": _BROWSER_UA, "Referer": f"{base}/jobs",
                   "Origin": base, "Content-Type": "application/json"}
        out: list[PostingStub] = []
        with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
            warm = client.get(f"{base}/jobs")            # mint the `ct` WAF/session cookie
            if warm.status_code != 200:
                _log.warning("paradox warmup non-200", extra={"host": host,
                                                              "status": warm.status_code})
                return []
            page = 1
            payload = {"disable_switch_search_mode": False, "site_available_languages": ["en"]}
            for _ in range(_MAX_PAGES):
                qs = urlencode({"page_number": page, "page_size": _PAGE,
                                "filter[country][0]": "United States"})
                r = client.post(f"{base}/api/get-jobs?{qs}", json=payload)
                if r.status_code != 200:                 # 403 => WAF (cookie expired / rate)
                    _log.warning("paradox get-jobs non-200",
                                 extra={"host": host, "status": r.status_code, "page": page})
                    break
                stubs, total = parse_response(r.json() or {})
                out.extend(stubs)
                if not stubs or page * _PAGE >= total:
                    break
                page += 1
        return out
