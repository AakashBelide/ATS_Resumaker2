"""Greenhouse board-listing adapter. Lists every open posting for a board token via the
public boards API (`boards-api.greenhouse.io/v1/boards/{token}/jobs`). The full JD is then
fetched on demand by `scrape/` using the per-job URL.

Bandwidth: Greenhouse supports conditional GET (ETag -> 304 Not Modified) and gzip, so on
an unchanged board we send `If-None-Match` and get a cheap 304 - the recommended way to
"avoid re-fetching old postings". A 304 returns [] (nothing new to ingest), which is
behaviorally identical to an unchanged board for dedupe.
"""
from __future__ import annotations

from resumaker.persistence import cache
from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_ETAG_NS = "gh_etag"


class GreenhouseSource:
    source = "greenhouse"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
        etag_key = cache.make_key(token)
        prior = cache.get(_ETAG_NS, etag_key)
        if prior:
            headers["If-None-Match"] = prior
        r = polite_get(api, headers)
        if r.status_code == 304:            # unchanged since last poll - nothing new
            return []
        r.raise_for_status()
        if r.headers.get("ETag"):
            cache.put(_ETAG_NS, etag_key, r.headers["ETag"])
        out: list[PostingStub] = []
        for j in r.json().get("jobs", []) or []:
            jid = str(j.get("id", ""))
            out.append(PostingStub(
                source=self.source,
                external_id=jid,
                # Canonical boards URL so the single-JD scraper hits the clean API path.
                # A company's `absolute_url` often points at its own site (no greenhouse.io
                # host), which would force a Playwright fallback - so we keep it in `extra`.
                url=f"https://boards.greenhouse.io/{token}/jobs/{jid}",
                title=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""),
                updated_at=j.get("updated_at", ""),
                extra={"absolute_url": j.get("absolute_url", "")},
            ))
        return out
