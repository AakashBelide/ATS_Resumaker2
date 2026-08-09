"""Eightfold ATS family adapter (`/api/apply/v2/jobs`). Powers Netflix, BCG, Qualcomm, etc.

A board is identified by its careers host + Eightfold `domain`, carried in BoardRef.extra:
    BoardRef(source="eightfold", token="netflix",
             extra={"host": "explore.jobs.netflix.net", "domain": "netflix.com"})
Clean public JSON, no auth/CAPTCHA. We request US locations server-side; the service still
applies the US + tech filters client-side.
"""
from __future__ import annotations

from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_PAGE = 50
_MAX_PAGES = 8


class EightfoldSource:
    source = "eightfold"

    def list_postings(self, token: str, *, host: str = "", domain: str = "",
                      **kwargs: str) -> list[PostingStub]:
        if not host or not domain:
            raise ValueError("eightfold board needs extra={'host':..., 'domain':...}")
        base = f"https://{host}/api/apply/v2/jobs"
        out: list[PostingStub] = []
        start = 0
        for _ in range(_MAX_PAGES):
            q = urlencode({"domain": domain, "location": "United States",
                           "start": start, "num": _PAGE, "sort_by": "relevance"})
            r = polite_get(f"{base}?{q}", {"User-Agent": UA})
            if r.status_code != 200:
                break
            body = r.json() or {}
            positions = body.get("positions", []) or []
            for p in positions:
                pid = str(p.get("id", "") or p.get("requisitionId", ""))
                out.append(PostingStub(
                    source=self.source,
                    external_id=pid,
                    url=p.get("canonicalPositionUrl", "") or f"https://{host}/careers/job/{pid}",
                    title=p.get("name", ""),
                    location=p.get("location", ""),
                    updated_at=str(p.get("t_create", "")),
                ))
            start += _PAGE
            if start >= int(body.get("count", 0) or 0) or not positions:
                break
        return out
