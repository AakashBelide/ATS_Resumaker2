"""IBM careers adapter (bespoke Elasticsearch search API). Single-company (token ignored).

IBM runs its own ES-style search service at www-api.ibm.com (not an ATS family). We POST a
literal ES query with a US country post-filter and page via from/size. Clean JSON, no auth,
no CSRF, no bot protection (verified 200 from datacenter IPs). The search index exposes no
posting date, so `updated_at` is empty and `first_seen` synthesizes freshness. US filter is
server-side (`field_keyword_05 = United States`) and re-checked client-side.
"""
from __future__ import annotations

import re

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_post
from resumaker.providers.sources.ua import UA

_URL = "https://www-api.ibm.com/search/api/v2"
_PAGE = 50
_MAX_PAGES = 12
_JOBID_RE = re.compile(r"[?&]jobId=(\d+)")


def _query(frm: int) -> dict:
    return {
        "appId": "careers", "scopes": ["careers2"],
        "query": {"bool": {"must": []}},
        "post_filter": {"term": {"field_keyword_05": "United States"}},
        "size": _PAGE, "from": frm,
        "sort": [{"_score": "desc"}, {"pageviews": "desc"}],
        "lang": "zz", "localeSelector": {}, "sm": {"query": "", "lang": "zz"},
        "_source": ["id", "title", "url", "field_keyword_05", "field_keyword_19"]}


def parse_response(body: dict) -> tuple[list[PostingStub], int]:
    """Parse an ES response into (stubs, total). Defensive to shape drift."""
    hits = ((body or {}).get("hits") or {})
    total = int(((hits.get("total") or {}).get("value")) or 0)
    out: list[PostingStub] = []
    for h in hits.get("hits") or []:
        src = h.get("_source") or {}
        url = src.get("url", "")
        m = _JOBID_RE.search(url)
        ext = m.group(1) if m else str(src.get("id", "") or h.get("_id", ""))
        out.append(PostingStub(
            source="ibm", external_id=ext, url=url,
            title=src.get("title", ""),
            location=str(src.get("field_keyword_19", "") or src.get("field_keyword_05", "")),
            updated_at=""))                            # not exposed by the search index
    return out, total


class IBMSource:
    source = "ibm"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        headers = {"User-Agent": UA, "Content-Type": "application/json"}
        out: list[PostingStub] = []
        frm = 0
        for _ in range(_MAX_PAGES):
            r = polite_post(_URL, headers, json=_query(frm))
            if r.status_code != 200:
                break
            stubs, total = parse_response(r.json() or {})
            out.extend(stubs)
            frm += _PAGE
            if not stubs or frm >= total:
                break
        return out
