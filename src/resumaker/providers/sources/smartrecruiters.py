"""SmartRecruiters family adapter (public postings API). Covers Atlassian, etc.

    BoardRef(source="smartrecruiters", token="Atlassian")
`api.smartrecruiters.com/v1/companies/{company}/postings` - clean public JSON, no auth.
"""
from __future__ import annotations

from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_PAGE = 100
_MAX_PAGES = 6


class SmartRecruitersSource:
    source = "smartrecruiters"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        base = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
        out: list[PostingStub] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            q = urlencode({"limit": _PAGE, "offset": offset, "country": "us"})
            r = polite_get(f"{base}?{q}", {"User-Agent": UA})
            if r.status_code != 200:
                break
            body = r.json() or {}
            content = body.get("content", []) or []
            for p in content:
                loc = p.get("location", {}) or {}
                city = ", ".join(x for x in (loc.get("city"), loc.get("region"),
                                             loc.get("country")) if x)
                out.append(PostingStub(
                    source=self.source,
                    external_id=str(p.get("id", "")),
                    url=(p.get("applyUrl", "")
                         or f"https://jobs.smartrecruiters.com/{token}/{p.get('id','')}"),
                    title=p.get("name", ""),
                    location=city,
                    updated_at=str(p.get("releasedDate", "")),
                ))
            offset += _PAGE
            if offset >= int(body.get("totalFound", 0) or 0) or not content:
                break
        return out
