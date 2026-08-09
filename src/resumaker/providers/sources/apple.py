"""Apple jobs adapter (`jobs.apple.com/api/v1/search`). Single-company.

Apple requires a CSRF handshake (no login): GET a search page to receive the `jobs` cookie
+ a 64-hex CSRF token embedded in the HTML, then POST the search with a matched
`X-Apple-CSRF-Token`. Both must come from the same client/session. We query US, newest-
first; the service applies the tech filter client-side.
"""
from __future__ import annotations

import re

import httpx

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.ua import UA

_log = get_logger("resumaker.sources.apple")
_SEARCH = "https://jobs.apple.com/api/v1/search"
_PAGE = 20
_MAX_PAGES = 10
_CSRF_RE = re.compile(r"[a-f0-9]{64}")


class AppleSource:
    source = "apple"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        out: list[PostingStub] = []
        with httpx.Client(headers={"User-Agent": UA}, timeout=30,
                          follow_redirects=True) as c:
            pg = c.get("https://jobs.apple.com/en-us/search")
            m = _CSRF_RE.search(pg.text)
            if not m:
                _log.warning("apple: no CSRF token found")
                return out
            headers = {"X-Apple-CSRF-Token": m.group(0), "Content-Type": "application/json"}
            for page in range(1, _MAX_PAGES + 1):
                body = {"query": "", "filters": {"locations": ["postLocation-USA"]},
                        "page": page, "locale": "en-us", "sort": "newest",
                        "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"}}
                r = c.post(_SEARCH, headers=headers, json=body)
                if r.status_code != 200:
                    break
                res = (r.json() or {}).get("res") or {}
                jobs = res.get("searchResults") or []
                for j in jobs:
                    loc = (j.get("locations") or [{}])[0]
                    loc_str = ", ".join(x for x in (loc.get("name"), loc.get("stateProvince"),
                                                    loc.get("countryName")) if x)
                    pos = j.get("positionId", "")
                    slug = j.get("transformedPostingTitle", "")
                    out.append(PostingStub(
                        source=self.source,
                        external_id=str(j.get("id", "") or pos),
                        url=f"https://jobs.apple.com/en-us/details/{pos}/{slug}",
                        title=j.get("postingTitle", ""),
                        location=loc_str,
                        updated_at=str(j.get("postDateInGMT", "")),
                    ))
                if not jobs or page * _PAGE >= int(res.get("totalRecords", 0) or 0):
                    break
        return out
