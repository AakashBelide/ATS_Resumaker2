"""Greenhouse board-listing adapter. Lists every open posting for a board token via the
public boards API (`boards-api.greenhouse.io/v1/boards/{token}/jobs`). The full JD is then
fetched on demand by `scrape/` using the per-job URL. This is the reference adapter proving
the `sources/` seam; Lever/Ashby/Workday follow the same shape in the RI phase.
"""
from __future__ import annotations

import httpx

from resumaker.providers.sources.base import PostingStub

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class GreenhouseSource:
    source = "greenhouse"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        r = httpx.get(api, headers={"User-Agent": _UA}, timeout=20, follow_redirects=True)
        r.raise_for_status()
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
