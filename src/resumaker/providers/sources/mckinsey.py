"""McKinsey careers adapter (proprietary Solr-style API behind gateway.mckinsey.com).

Single-company (token is ignored). `countries=United States` server-side; the service
still applies US + tech filters. Freshness is weak (no clean posting date) - we fall back
to `first_seen`.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_BASE = "https://gateway.mckinsey.com/apigw-x0cceuow60/v1/api/jobs/search"
_PAGE = 100
_MAX_PAGES = 4


_BASE_URL = "https://www.mckinsey.com/careers/search-jobs/jobs"


def mckinsey_job_url(title: str, jid: str) -> str:
    """Best-effort constructor for the public McKinsey job URL `<slug>-<id>`.

    IMPORTANT: the slug is generated SERVER-SIDE and is NOT reliably derivable from the
    title, so this is only a fallback. The API returns the authoritative slug in the
    `friendlyURL` field (already `<slug>-<id>`); `list_postings` prefers that and only falls
    back here when it is missing. See RESUME_SYSTEM_BLUEPRINT context.

    The observed server rule (validated against 100/100 live `friendlyURL`s): lowercase, keep
    ASCII hyphen-minus '-' (collapsing runs to one), STRIP every other non-alphanumeric -
    including spaces, commas, slashes and en/em dashes. That is why
    'Knowledge Graph Data Engineer - QuantumBlack, ...' (en-dash '–') slugs to
    '...engineerquantumblack...' (no hyphen), while
    'Senior Knowledge Graph Data Engineer - QuantumBlack, ...' (ASCII '-') keeps the hyphen:
    '...engineer-quantumblack...'. The bare-id form ('.../jobs/110946') redirects to a
    'no longer available' page, so we still want the slug when we can."""
    s = (title or "").lower()
    s = re.sub(r"-+", "-", s)                  # collapse runs of ASCII hyphen-minus
    s = re.sub(r"[^a-z0-9-]+", "", s)          # strip spaces/punct/en-em dashes
    slug = re.sub(r"-+", "-", s).strip("-")
    return f"{_BASE_URL}/{slug}-{jid}" if slug and jid else f"{_BASE_URL}/{jid}"


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
                title = d.get("title", "") or d.get("jobTitle", "")
                # Authoritative public URL: the API returns `friendlyURL` = '<slug>-<id>'
                # with the server-generated slug. Prefer it over any client-side guess.
                # (`jobApplyURL` is an Avature apply link, not the public careers page.)
                friendly = str(d.get("friendlyURL", "") or "").strip()
                url = f"{_BASE_URL}/{friendly}" if friendly else mckinsey_job_url(title, jid)
                out.append(PostingStub(
                    source=self.source,
                    external_id=jid,
                    url=url,
                    title=title,
                    location=str(loc),
                    updated_at=str(d.get("postedToLinkedInDate", "")),
                ))
            start += _PAGE
            if start > int(body.get("numFound", 0) or 0) or not docs:
                break
        return out
