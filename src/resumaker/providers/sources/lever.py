"""Lever board-listing adapter. Lists all postings for a company via the public API
(`api.lever.co/v0/postings/{company}?mode=json`)."""
from __future__ import annotations

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA


class LeverSource:
    source = "lever"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        api = f"https://api.lever.co/v0/postings/{token}?mode=json"
        r = polite_get(api, {"User-Agent": UA})
        r.raise_for_status()
        out: list[PostingStub] = []
        for j in r.json() or []:
            out.append(PostingStub(
                source=self.source,
                external_id=str(j.get("id", "")),
                url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
                title=j.get("text", ""),
                location=(j.get("categories") or {}).get("location", ""),
                updated_at=str(j.get("createdAt", "")),
            ))
        return out
