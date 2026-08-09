"""Ashby board-listing adapter. Lists all postings for a company via the public
job-board API (`api.ashbyhq.com/posting-api/job-board/{company}`).

Field notes (verified): the date field is `publishedAt` (there is no `publishedDate`),
and the API returns both listed and unlisted postings - we keep only `isListed` ones."""
from __future__ import annotations

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA


class AshbySource:
    source = "ashby"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        api = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
        r = polite_get(api, {"User-Agent": UA})
        r.raise_for_status()
        out: list[PostingStub] = []
        for j in r.json().get("jobs", []) or []:
            if j.get("isListed") is False:          # skip unlisted/draft postings
                continue
            # Ashby publishes a clean pay range in disclosure states; empty otherwise.
            comp = str((j.get("compensation") or {}).get("compensationTierSummary") or "")
            out.append(PostingStub(
                source=self.source,
                external_id=str(j.get("id", "")),
                url=j.get("jobUrl", "") or j.get("applyUrl", ""),
                title=j.get("title", ""),
                location=j.get("location", ""),
                updated_at=str(j.get("publishedAt", "")),
                comp=comp,
            ))
        return out
