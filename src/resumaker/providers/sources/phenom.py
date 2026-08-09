"""Phenom People family adapter (`/widgets` refineSearch). Covers MITRE, Dassault, FedEx,
Wayfair, Takeda, AMD, etc.

A board is its widgets URL + page id, in BoardRef.extra:
    BoardRef(source="phenom", token="mitre",
             extra={"url": "https://careers.mitre.org/widgets", "page_id": "page21",
                    "country": "us"})
POST with ddoKey='refineSearch' (the page's default eagerLoad key needs a session token;
refineSearch works anonymously). Clean JSON, no CAPTCHA.
"""
from __future__ import annotations

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_post
from resumaker.providers.sources.ua import UA

_PAGE = 50
_MAX_PAGES = 6


class PhenomSource:
    source = "phenom"

    def list_postings(self, token: str, *, url: str = "", page_id: str = "",
                      country: str = "us", **kwargs: str) -> list[PostingStub]:
        if not url or not page_id:
            raise ValueError("phenom board needs extra={'url':..., 'page_id':...}")
        headers = {"User-Agent": UA, "Content-Type": "application/json",
                   "X-Requested-With": "XMLHttpRequest"}
        out: list[PostingStub] = []
        frm = 0
        for _ in range(_MAX_PAGES):
            payload = {"lang": "en_us", "deviceType": "desktop", "country": country,
                       "pageName": "search-results", "ddoKey": "refineSearch",
                       "from": frm, "size": _PAGE, "jobs": True, "counts": True,
                       "all_fields": ["category", "state", "city", "country"],
                       "keywords": "", "selected_fields": {}, "siteType": "external",
                       "pageId": page_id, "global": True}
            r = polite_post(url, headers, json=payload)
            if r.status_code != 200:
                break
            rs = (r.json() or {}).get("refineSearch") or {}
            jobs = ((rs.get("data") or {}).get("jobs")) or []
            for j in jobs:
                loc = j.get("cityStateCountry") or j.get("location") or ", ".join(
                    x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
                out.append(PostingStub(
                    source=self.source,
                    external_id=str(j.get("jobId", "") or j.get("jobSeqNo", "")),
                    url=j.get("applyUrl", "") or j.get("jobUrl", "") or j.get("url", ""),
                    title=j.get("title", ""),
                    location=str(loc),
                    updated_at=str(j.get("postedDate", "") or j.get("dateCreated", "")),
                ))
            frm += _PAGE
            if frm >= int(rs.get("totalHits", 0) or 0) or not jobs:
                break
        return out
