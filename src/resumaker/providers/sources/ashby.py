"""Ashby board-listing adapter. Lists all postings for a company via the public
job-board API (`api.ashbyhq.com/posting-api/job-board/{company}`)."""
from __future__ import annotations

import httpx

from resumaker.providers.sources.base import PostingStub

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class AshbySource:
    source = "ashby"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        api = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
        r = httpx.get(api, headers={"User-Agent": _UA}, timeout=20, follow_redirects=True)
        r.raise_for_status()
        out: list[PostingStub] = []
        for j in r.json().get("jobs", []) or []:
            out.append(PostingStub(
                source=self.source,
                external_id=str(j.get("id", "")),
                url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                title=j.get("title", ""),
                location=j.get("location", ""),
                updated_at=str(j.get("publishedDate", "")),
            ))
        return out
