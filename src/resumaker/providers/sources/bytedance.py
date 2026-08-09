"""ByteDance / TikTok adapter (`api.lifeattiktok.com` supplier search). Single-company.

Requires the header `website-path: tiktok`. There is no working country code, so US is
requested via an explicit list of US city codes (server-side filter). Location comes from
city_info (city + parent state); the service still applies the tech filter client-side.
The US city-code list is a static map that may need occasional refresh.
"""
from __future__ import annotations

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_post
from resumaker.providers.sources.ua import UA

_URL = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
# US city codes (from research); TikTok has no single USA country code that works.
_US_CITY_CODES = ["CT_75", "CT_114", "CT_157", "CT_243", "CT_1103355", "CT_247", "CT_94",
                  "CT_203", "CT_221", "CT_1103554", "CT_223", "CT_233", "CT_1000001"]
_PAGE = 50
_MAX_PAGES = 8


class ByteDanceSource:
    source = "bytedance"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        headers = {"User-Agent": UA, "Content-Type": "application/json",
                   "website-path": "tiktok"}
        out: list[PostingStub] = []
        offset = 0
        for _ in range(_MAX_PAGES):
            body = {"keyword": "", "limit": _PAGE, "offset": offset,
                    "location_code_list": _US_CITY_CODES, "job_category_id_list": [],
                    "subject_id_list": [], "recruitment_id_list": []}
            r = polite_post(_URL, headers, json=body)
            if r.status_code != 200:
                break
            data = (r.json() or {}).get("data") or {}
            jobs = data.get("job_post_list") or []
            for j in jobs:
                ci = j.get("city_info") or {}
                parent = ci.get("parent") or {}
                loc = ", ".join(x for x in (ci.get("en_name"), parent.get("en_name")) if x)
                jid = str(j.get("id", ""))
                out.append(PostingStub(
                    source=self.source,
                    external_id=jid,
                    url=f"https://lifeattiktok.com/search/{jid}",
                    title=j.get("title", ""),
                    location=loc,
                    updated_at=str((j.get("job_post_info") or {}).get("publish_time", "")),
                ))
            offset += _PAGE
            if not jobs or offset >= int(data.get("count", 0) or 0):
                break
        return out
