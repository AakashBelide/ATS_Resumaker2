"""Microsoft careers adapter (GCS - Global Careers Site - JSON API). Single-company.

Endpoint: gcsservices.careers.microsoft.com/search/api/v1/search (public, no auth). Clean
JSON, but the host is fronted by Azure Front Door whose edge routing 4xx's some datacenter
IPs (NOT a CAPTCHA) - so this cannot be verified from CI/VM sandboxes and must be confirmed
from a normal (residential) network. The response PARSER is unit-tested against a fixture;
only the live fetch is environment-gated.
"""
from __future__ import annotations

from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_BASE = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
_PAGE = 20
_MAX_PAGES = 8


def parse_response(body: dict) -> tuple[list[PostingStub], int]:
    """Parse a GCS search response into (stubs, total). Defensive to shape drift."""
    res = ((body or {}).get("operationResult") or {}).get("result") \
        or (body or {}).get("result") or {}
    jobs = res.get("jobs") or []
    total = int(res.get("totalJobs") or res.get("total") or 0)
    out: list[PostingStub] = []
    for j in jobs:
        props = j.get("properties") or {}
        locs = props.get("locations")
        if not locs:
            pl = props.get("primaryLocation") or j.get("location")
            locs = [pl] if pl else []
        loc = ", ".join(str(x) for x in locs[:2]) if isinstance(locs, list) else str(locs)
        jid = str(j.get("jobId") or j.get("id") or "")
        out.append(PostingStub(
            source="microsoft", external_id=jid,
            url=f"https://jobs.careers.microsoft.com/global/en/job/{jid}",
            title=j.get("title", ""), location=loc,
            updated_at=str(props.get("postingDate", "") or j.get("postingDate", "")),
        ))
    return out, total


class MicrosoftSource:
    source = "microsoft"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        headers = {"User-Agent": UA, "Referer": "https://careers.microsoft.com/"}
        out: list[PostingStub] = []
        for pg in range(1, _MAX_PAGES + 1):
            q = urlencode({"q": "", "lc": "United States", "l": "en_us", "pg": pg,
                           "pgSz": _PAGE, "o": "Recent", "flt": "true"})
            r = polite_get(f"{_BASE}?{q}", headers)
            if r.status_code != 200:
                break
            stubs, total = parse_response(r.json() or {})
            out.extend(stubs)
            if not stubs or pg * _PAGE >= total:
                break
        return out
