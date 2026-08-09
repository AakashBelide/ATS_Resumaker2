"""McKinsey careers adapter (proprietary Solr-style API behind gateway.mckinsey.com).

Single-company (token is ignored). `countries=United States` server-side; the service
still applies US + tech filters. Freshness is weak (no clean posting date) - we fall back
to `first_seen`.
"""
from __future__ import annotations

from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_BASE = "https://gateway.mckinsey.com/apigw-x0cceuow60/v1/api/jobs/search"
_PAGE = 100
_MAX_PAGES = 4


class McKinseySource:
    source = "mckinsey"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        headers = {"User-Agent": UA, "Referer": "https://www.mckinsey.com/careers/search-jobs"}
        out: list[PostingStub] = []
        start = 1
        for _ in range(_MAX_PAGES):
            q = urlencode({"pageSize": _PAGE, "start": start, "lang": "en",
                           "countries": "United States"})
            r = polite_get(f"{_BASE}?{q}", headers)
            if r.status_code != 200:
                break
            body = r.json() or {}
            docs = body.get("docs", []) or []
            for d in docs:
                loc = d.get("cities") or d.get("locations") or d.get("city") or ""
                if isinstance(loc, list):
                    loc = ", ".join(str(x) for x in loc[:2])
                jid = str(d.get("jobID", "") or d.get("id", ""))
                out.append(PostingStub(
                    source=self.source,
                    external_id=jid,
                    url=d.get("jobApplyUrl", "") or d.get("url", "")
                        or f"https://www.mckinsey.com/careers/search-jobs/jobs/{jid}",
                    title=d.get("jobTitle", "") or d.get("title", ""),
                    location=str(loc),
                    updated_at=str(d.get("postedToLinkedInDate", "")),
                ))
            start += _PAGE
            if start > int(body.get("numFound", 0) or 0) or not docs:
                break
        return out
