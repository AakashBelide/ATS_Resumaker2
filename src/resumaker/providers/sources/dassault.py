"""Dassault Systemes adapter (3DS Exalead 'card search' API). Single-company.

Hits the public Exalead endpoint that powers www.3ds.com/careers/jobs. The response is
Exalead XML (not JSON): each posting is a <Hit> block of <Meta name="X"><MetaString
name="value">V</MetaString> pairs. Two refinements matter (from career-ops): the
`card_content_type/career` facet (Dassault's own jobs, not aggregated content) and the
`cards language/en` facet (collapse the ~12-language duplicates to the English copy).
Ported from career-ops's dassault provider.
"""
from __future__ import annotations

import re

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_BASE = "https://www.3ds.com/apisearch/card_search_api"
_REFINES = "&r=f/card_content_type/career&r=f/card_content_categories_facet/cards%20language/en"
_PAGE = 10
_MAX_PAGES = 40
_META = re.compile(
    r'<Meta name="([^"]+)"[^>]*>\s*<MetaString[^>]*name="value"[^>]*>([\s\S]*?)</MetaString>')
# content_categories is "Label/Value Label/Value ..."; slice each value up to the next label.
_LABELS = ("Category", "Type", "Country", "City", "Products", "Year")
_LABEL_RE = re.compile(r"(^|\s)(" + "|".join(_LABELS) + r")/")


def _meta_map(hit: str) -> dict:
    m: dict = {}
    for name, val in _META.findall(hit):
        m.setdefault(name, val)
    return m


def _city_country(categories: str) -> str:
    marks = [(mm.group(2), mm.start() + len(mm.group(1)), mm.end())
             for mm in _LABEL_RE.finditer(categories)]
    city = country = ""
    for i, (label, _ks, vstart) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(categories)
        val = categories[vstart:end].strip()
        if label == "City" and not city:
            city = val
        elif label == "Country" and not country:
            country = val
    return ", ".join(x for x in (city, country) if x)


class DassaultSource:
    source = "dassault"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        out: list[PostingStub] = []
        for page in range(_MAX_PAGES):
            url = f"{_BASE}?lang=en{_REFINES}&start={page * _PAGE}"
            r = polite_get(url, {"User-Agent": UA})
            if r.status_code != 200:
                break
            xml = r.text
            hits = xml.split("<Hit ")[1:]
            if not hits:
                break
            for hit in hits:
                m = _meta_map(hit)
                title = m.get("content_title", "").strip()
                job_url = m.get("content_cta_1_url", "").strip()
                if not title or "3ds.com" not in job_url:      # safety: keep only 3ds jobs
                    continue
                out.append(PostingStub(
                    source=self.source,
                    external_id=m.get("card_id", "") or job_url,
                    url=job_url,
                    title=title,
                    location=_city_country(m.get("content_categories", "")),
                    updated_at=m.get("content_start_datetime", ""),
                ))
            nhits = re.search(r'nhits="(\d+)"', xml)
            if nhits and (page + 1) * _PAGE >= int(nhits.group(1)):
                break
        return out
