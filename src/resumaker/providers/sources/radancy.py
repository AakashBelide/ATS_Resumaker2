"""Radancy (TalentBrew) family adapter. Covers Takeda and other TalentBrew career sites.

Uses the cheap JSON-fragment endpoint the page's own JS calls (not the multi-MB HTML
page): GET {origin}/{lang}/search-jobs/results?RecordsPerPage=100&SearchResultsModuleName=
Search Results&CurrentPage=N -> {"results": "<html cards>", ...}. We parse the job anchors
(id + title + location). Ported from career-ops's radancy provider (legacy markup).

    BoardRef(source="radancy", token="takeda",
             extra={"origin": "https://jobs.takeda.com", "lang": "en"})
"""
from __future__ import annotations

import html
import re
from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_MAX_PAGES = 30
# One job = an <a href=".../job/..." data-job-id="N"> ... <h2>title</h2> ...
# <span class="location">loc</span> ... </a>
_ANCHOR = re.compile(
    r'<a[^>]*href="([^"]*/job/[^"]+)"[^>]*data-job-id="(\d+)"[^>]*>([\s\S]*?)</a>')
_TITLE = re.compile(r'<h2[^>]*>([\s\S]*?)</h2>')
_LOC = re.compile(r'class="location"[^>]*>([\s\S]*?)</span>')


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]*>", " ", s)).replace("\xa0", " ").strip()


class RadancySource:
    source = "radancy"

    def list_postings(self, token: str, *, origin: str = "", lang: str = "en",
                      **kwargs: str) -> list[PostingStub]:
        if not origin:
            raise ValueError("radancy board needs extra={'origin':..., 'lang':...}")
        base = f"{origin}/{lang}/search-jobs/results"
        out: list[PostingStub] = []
        page = 1
        total_pages = 1
        for _ in range(_MAX_PAGES):
            q = urlencode({"RecordsPerPage": 100, "SearchResultsModuleName": "Search Results",
                           "CurrentPage": page})
            r = polite_get(f"{base}?{q}", {"User-Agent": UA})
            if r.status_code != 200:
                break
            res = html.unescape((r.json() or {}).get("results", "") or "")
            tp = re.search(r'data-total-pages="(\d+)"', res)
            total_pages = int(tp.group(1)) if tp else total_pages
            found = 0
            for m in _ANCHOR.finditer(res):
                href, jid, inner = m.group(1), m.group(2), m.group(3)
                tt = _TITLE.search(inner)
                title = _clean(tt.group(1)) if tt else ""
                if not title:
                    continue
                loc = _LOC.search(inner)
                out.append(PostingStub(
                    source=self.source, external_id=jid, url=origin + href,
                    title=title, location=_clean(loc.group(1)) if loc else ""))
                found += 1
            page += 1
            if found == 0 or page > total_pages:
                break
        return out
