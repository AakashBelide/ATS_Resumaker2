"""Google careers adapter. Single-company (token ignored).

Google retired its old `careers.google.com/api/v3` REST endpoint (404). The current site
(google.com/about/careers/applications) is a server-rendered app: the full job list + total
count are embedded in the page HTML as a JSON blob inside an
`AF_initDataCallback({key: 'ds:1', ... data:[...]})` script. We fetch that page and parse the
blob - no auth, no CSRF, no bot protection (verified reachable from datacenter IPs). Each job
is a positional (index-based) array; the field indices are documented in `_job_stub`. Fixed
20 results/page server-side. US filtering via `location=United States` + client-side gate.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlencode

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_BASE = "https://www.google.com/about/careers/applications/jobs/results/"
_PAGE = 20            # server-fixed page size
_MAX_PAGES = 15
_DS1 = re.compile(r"AF_initDataCallback\(\{key:\s*'ds:1'[^\n]*?data:")


def _epoch_to_iso(v: object) -> str:
    """Google times are `[epochSeconds, nanos]`; return an ISO date (or '')."""
    if isinstance(v, list) and v and isinstance(v[0], int | float):
        return datetime.fromtimestamp(v[0], UTC).isoformat()
    return ""


def _job_stub(rec: list) -> PostingStub | None:
    """Map one positional job record to a stub. Indices per the ds:1 schema:
    [0]=id [1]=title [2]=apply-url [9]=locations [14]=publish-time [13]=update-time."""
    if not isinstance(rec, list) or len(rec) < 3:
        return None
    jid = str(rec[0] or "")
    if not jid:
        return None
    loc = ""
    locs = rec[9] if len(rec) > 9 else None
    if isinstance(locs, list) and locs and isinstance(locs[0], list) and locs[0]:
        loc = str(locs[0][0] or "")                    # first location's display string
    updated = _epoch_to_iso(rec[14] if len(rec) > 14 else None) \
        or _epoch_to_iso(rec[13] if len(rec) > 13 else None)
    return PostingStub(
        source="google", external_id=jid,
        url=f"{_BASE}{jid}", title=str(rec[1] or ""), location=loc, updated_at=updated)


def parse_response(html: str) -> tuple[list[PostingStub], int]:
    """Extract (stubs, total) from a results page. `data[0]`=jobs, `data[2]`=total count."""
    m = _DS1.search(html or "")
    if not m:
        return [], 0
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
    except (json.JSONDecodeError, ValueError):
        return [], 0
    if not isinstance(data, list) or not data:
        return [], 0
    jobs = data[0] if isinstance(data[0], list) else []
    total = int(data[2]) if len(data) > 2 and isinstance(data[2], int) else len(jobs)
    stubs = [s for rec in jobs if (s := _job_stub(rec)) is not None]
    return stubs, total


class GoogleSource:
    source = "google"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        headers = {"User-Agent": UA, "Accept": "text/html"}
        out: list[PostingStub] = []
        for page in range(1, _MAX_PAGES + 1):
            q = urlencode({"location": "United States", "page": page})
            r = polite_get(f"{_BASE}?{q}", headers)
            if r.status_code != 200:
                break
            stubs, total = parse_response(r.text)
            out.extend(stubs)
            if not stubs or page * _PAGE >= total:
                break
        return out
