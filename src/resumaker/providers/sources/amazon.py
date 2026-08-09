"""Amazon jobs adapter (`amazon.jobs/en/search.json`). Covers Amazon and AWS (AWS roles
live on the same board, scoped by `team=AWS` via BoardRef.extra). Clean public JSON, no
auth/CAPTCHA. We request US + newest-first server-side; the service applies the US + tech
filters client-side.
"""
from __future__ import annotations

from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_BASE = "https://www.amazon.jobs/en/search.json"
_PAGE = 100
_MAX_PAGES = 4


class AmazonJobsSource:
    source = "amazon"

    def list_postings(self, token: str, *, team: str = "", **kwargs: str) -> list[PostingStub]:
        out: list[PostingStub] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            params = [("normalized_country_code[]", "USA"), ("result_limit", _PAGE),
                      ("offset", offset), ("sort", "recent"), ("base_query", "")]
            if team:
                params.append(("team", team))
            q = urlencode(params)
            r = polite_get(f"{_BASE}?{q}", {"User-Agent": UA})
            if r.status_code != 200:
                break
            body = r.json() or {}
            jobs = body.get("jobs", []) or []
            for j in jobs:
                out.append(PostingStub(
                    source=self.source,
                    external_id=str(j.get("id_icims", "") or j.get("id", "")),
                    url="https://www.amazon.jobs" + (j.get("job_path", "") or ""),
                    title=j.get("title", ""),
                    location=j.get("normalized_location", ""),
                    updated_at=str(j.get("posted_date", "")),
                ))
            offset += _PAGE
            if offset >= int(body.get("hits", 0) or 0) or not jobs:
                break
        return out
