"""Goldman Sachs careers adapter (proprietary GraphQL at api-higher.gs.com).

Single-company (token ignored). The gateway rejects populated server-side filters for
direct clients, so we send an empty `filters:[]` and do US + tech filtering client-side.
`lastPostedDate` gives freshness.
"""
from __future__ import annotations

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_post
from resumaker.providers.sources.ua import UA

_URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
_QUERY = ("query GetRoles($searchQueryInput: RoleSearchQueryInput!){"
          "roleSearch(searchQueryInput:$searchQueryInput){totalCount items{"
          "roleId jobTitle jobFunction division lastPostedDate "
          "locations{primary city state country}}}}")
_PAGE = 50
_MAX_PAGES = 4


class GoldmanSource:
    source = "goldman"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        headers = {"User-Agent": UA, "Content-Type": "application/json",
                   "Referer": "https://higher.gs.com/"}
        out: list[PostingStub] = []
        for page in range(_MAX_PAGES):
            payload = {"operationName": "GetRoles", "query": _QUERY, "variables": {
                "searchQueryInput": {
                    "page": {"pageSize": _PAGE, "pageNumber": page},
                    "sort": {"sortStrategy": "RELEVANCE", "sortOrder": "DESC"},
                    "filters": [], "experiences": ["EARLY_CAREER", "PROFESSIONAL"],
                    "searchTerm": ""}}}
            r = polite_post(_URL, headers, json=payload)
            if r.status_code != 200:
                break
            search = ((r.json() or {}).get("data") or {}).get("roleSearch") or {}
            items = search.get("items", []) or []
            for it in items:
                locs = it.get("locations", []) or []
                loc = next((x for x in locs if x.get("primary")), locs[0] if locs else {})
                loc_str = ", ".join(x for x in (loc.get("city"), loc.get("state"),
                                                loc.get("country")) if x)
                rid = str(it.get("roleId", ""))
                out.append(PostingStub(
                    source=self.source,
                    external_id=rid,
                    url=f"https://higher.gs.com/roles/{rid}",
                    title=it.get("jobTitle", ""),
                    location=loc_str,
                    updated_at=str(it.get("lastPostedDate", "")),
                ))
            if (page + 1) * _PAGE >= int(search.get("totalCount", 0) or 0) or not items:
                break
        return out
