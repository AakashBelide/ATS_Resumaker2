"""Workday board-listing adapter via the CxS jobs endpoint (JSON, paginated).

Workday sits behind Akamai (TLS/JA3 fingerprinting), so we impersonate Chrome with
curl_cffi. A board needs the tenant host + site path, passed via the BoardRef `extra`:
    BoardRef(source="workday", token="<tenant>",
             extra={"host": "<tenant>.wd1.myworkdayjobs.com", "site": "External"})
The emitted URL matches the single-JD Workday scraper so the full JD is fetched cleanly.
"""
from __future__ import annotations

from resumaker.providers.sources.base import PostingStub

_MAX_PAGES = 8
_PAGE = 20


class WorkdaySource:
    source = "workday"

    def list_postings(self, token: str, *, host: str = "", site: str = "",
                      **kwargs: str) -> list[PostingStub]:
        if not host or not site:
            raise ValueError("workday board needs extra={'host':..., 'site':...}")
        from curl_cffi import requests as cffi
        cxs = f"https://{host}/wday/cxs/{token}/{site}/jobs"
        out: list[PostingStub] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            r = cffi.post(cxs, impersonate="chrome", timeout=30,
                          json={"appliedFacets": {}, "limit": _PAGE, "offset": offset,
                                "searchText": ""})
            if r.status_code != 200:
                break
            body = r.json() or {}
            postings = body.get("jobPostings", []) or []
            for jp in postings:
                ext = jp.get("externalPath", "")
                req_id = (jp.get("bulletFields") or [""])[0]
                out.append(PostingStub(
                    source=self.source,
                    external_id=str(req_id or ext),
                    url=f"https://{host}/{site}{ext}",
                    title=jp.get("title", ""),
                    location=jp.get("locationsText", ""),
                ))
            offset += _PAGE
            if offset >= int(body.get("total", 0) or 0) or not postings:
                break
        return out
