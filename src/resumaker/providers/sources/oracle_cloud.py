"""Oracle Recruiting Cloud (Candidate Experience) family adapter. Covers JPMC, Amex,
Citizens, Akamai, Staples, Ford, Oracle, etc. Clean public JSON REST, no auth/CAPTCHA.

A board is its Oracle host + site number, in BoardRef.extra:
    BoardRef(source="oracle_cloud", token="jpmc",
             extra={"host": "jpmc.fa.oraclecloud.com", "site": "CX_1001"})
We sort newest-first server-side; US + tech filtering is done client-side on the item's
PrimaryLocationCountry / JobFunction (facet IDs are tenant-specific, so client-side is
the robust choice).
"""
from __future__ import annotations

from urllib.parse import quote

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_get
from resumaker.providers.sources.ua import UA

_PAGE = 25
_MAX_PAGES = 6


class OracleCloudSource:
    source = "oracle_cloud"

    def list_postings(self, token: str, *, host: str = "", site: str = "",
                      **kwargs: str) -> list[PostingStub]:
        if not host or not site:
            raise ValueError("oracle_cloud board needs extra={'host':..., 'site':...}")
        api = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        out: list[PostingStub] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            finder = (f"findReqs;siteNumber={site},limit={_PAGE},"
                      f"sortBy=POSTING_DATES_DESC,offset={offset}")
            url = (f"{api}?onlyData=true"
                   f"&expand=requisitionList.secondaryLocations,flexFieldsFacet.values"
                   f"&finder={quote(finder, safe='=,;')}")
            r = polite_get(url, {"User-Agent": UA})
            if r.status_code != 200:
                break
            items = (r.json() or {}).get("items", []) or []
            total: int = 0
            reqs: list[dict] = []
            for item in items:
                total = int(item.get("TotalJobsCount", 0) or total)
                reqs.extend(item.get("requisitionList", []) or [])
            for rq in reqs:
                rid = str(rq.get("Id", ""))
                loc = rq.get("PrimaryLocation", "")
                if rq.get("PrimaryLocationCountry") and rq["PrimaryLocationCountry"] not in loc:
                    loc = f"{loc}, {rq['PrimaryLocationCountry']}"
                out.append(PostingStub(
                    source=self.source,
                    external_id=rid,
                    url=(f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}"),
                    title=rq.get("Title", ""),
                    location=loc,
                    updated_at=str(rq.get("PostedDate", "")),
                ))
            offset += _PAGE
            if not reqs or (total and offset >= total):
                break
        return out
