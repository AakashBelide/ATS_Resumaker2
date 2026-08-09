"""JibeApply / iCIMS-Jibe adapter (`/api/jobs`). Covers AMD and other Jibe-hosted boards
(iCIMS acquired Jibe; the JSON API is stable across tenants, incl. branded hosts).

    BoardRef(source="jibe", token="amd", extra={"host": "careers.amd.com"})
Also covers Atlassian (host="join.atlassian.com"). Clean public JSON, no auth/CAPTCHA.
Ported from career-ops's jibeapply provider.
"""
from __future__ import annotations

import json

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_MAX_PAGES = 40


def _load(r) -> dict:
    """Some Jibe tenants (e.g. Atlassian) emit raw control chars in HTML fields, which trip
    the strict JSON parser httpx uses. Fall back to a lenient parse before giving up."""
    try:
        return r.json() or {}
    except (json.JSONDecodeError, ValueError):
        try:
            return json.loads(r.text, strict=False) or {}
        except (json.JSONDecodeError, ValueError):
            return {}


class JibeApplySource:
    source = "jibe"

    def list_postings(self, token: str, *, host: str = "", **kwargs: str) -> list[PostingStub]:
        if not host:
            raise ValueError("jibe board needs extra={'host': '<careers host>'}")
        base = f"https://{host}/api/jobs"
        out: list[PostingStub] = []
        page = 1
        page_size = 0
        for _ in range(_MAX_PAGES):
            r = polite_get(f"{base}?page={page}", {"User-Agent": UA})
            if r.status_code != 200:
                break
            body = _load(r)
            items = body.get("jobs") or []
            for it in items:
                d = (it or {}).get("data") or it or {}
                slug = d.get("slug") or d.get("req_id")
                title = str(d.get("title", "")).strip()
                if not title or not slug:
                    continue
                loc = d.get("full_location") or ", ".join(
                    x for x in (d.get("city"), d.get("country")) if x)
                out.append(PostingStub(
                    source=self.source,
                    external_id=str(slug),
                    url=f"https://{host}/jobs/{slug}",
                    title=title,
                    location=str(loc),
                    updated_at=str(d.get("posted_date", "") or d.get("create_date", "")),
                ))
            page_size = page_size or len(items)
            if not items or (page_size and len(items) < page_size):
                break
            page += 1
        return out
