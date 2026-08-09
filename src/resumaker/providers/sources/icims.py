"""iCIMS *classic* Career Portal adapter (server-rendered HTML). Covers Suffolk and other
tenants on the legacy iCIMS portal that expose no JSON/RSS (only the iframe HTML listing).

    BoardRef(source="icims", token="suffolk",
             extra={"host": "careers-suffolkconstruction.icims.com"})

Distinct from `jibe` (the modern iCIMS `/api/jobs` JSON): this tenant only serves HTML, so
we parse the `?in_iframe=1` search page's job rows. Clean (200 from datacenter, no bot
protection), just markup. The list rows carry no posting date, so `updated_at` is empty and
`first_seen` synthesizes freshness. Locations are normalized (`US-TX-Austin` -> `Austin, TX,
US`) so the US filter reads them; the service re-checks US client-side.
"""
from __future__ import annotations

import html as _html
import re

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_PAGE_SIZE = 20
_MAX_PAGES = 40
# Each job row anchors to /jobs/{id}/{slug}/job with a title="{id} - {Title}" attribute.
_ANCHOR = re.compile(
    r'href="(https://[^"]*?/jobs/(\d+)/[^"]*?/job)[^"]*"[^>]*title="(\d+)\s*-\s*([^"]*)"')
_LOC = re.compile(r'map-marker[\s\S]{0,200}?(US-[A-Z]{2}-[^<"|]+(?:\s*\|\s*US-[A-Z]{2}-[^<"|]+)*)')
_TOTAL_PAGES = re.compile(r'[Pp]age\s+\d+\s+of\s+(\d+)')
_US_TOK = re.compile(r'US-([A-Z]{2})-(.+)')


def total_pages(page_html: str) -> int:
    m = _TOTAL_PAGES.search(page_html or "")
    return int(m.group(1)) if m else 1


def _norm_location(raw: str) -> str:
    """`US-TX-Austin | US-TX-Wilmer` -> `Austin, TX, US` (first location, filter-friendly)."""
    first = raw.split("|")[0].strip()
    m = _US_TOK.match(first)
    if m:
        return f"{m.group(2).strip()}, {m.group(1)}, US"
    return _html.unescape(first)


def parse_page(page_html: str) -> list[PostingStub]:
    """Parse one iframe search page's job rows into stubs (location paired per row block)."""
    page_html = page_html or ""
    matches = list(_ANCHOR.finditer(page_html))
    out: list[PostingStub] = []
    for i, m in enumerate(matches):
        href, jid, _tid, title = m.group(1), m.group(2), m.group(3), m.group(4)
        block = page_html[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(page_html)]
        loc_m = _LOC.search(block)
        out.append(PostingStub(
            source="icims", external_id=jid, url=href,
            title=_html.unescape(title).strip(),
            location=_norm_location(loc_m.group(1)) if loc_m else "",
            updated_at=""))
    return out


class ICIMSSource:
    source = "icims"

    def list_postings(self, token: str, *, host: str = "", **kwargs: str) -> list[PostingStub]:
        if not host:
            raise ValueError("icims board needs extra={'host': ...}")
        base = f"https://{host}/jobs/search"
        out: list[PostingStub] = []
        pages = 1
        page = 0
        while page < pages and page < _MAX_PAGES:
            url = f"{base}?ss=1&pr={page}&in_iframe=1"
            r = polite_get(url, {"User-Agent": UA})
            if r.status_code != 200:
                break
            if page == 0:
                pages = total_pages(r.text)
            stubs = parse_page(r.text)
            if not stubs:
                break
            out.extend(stubs)
            page += 1
        return out
