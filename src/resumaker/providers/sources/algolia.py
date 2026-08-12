"""Algolia-backed careers adapter.

Many companies (e.g. Rippling) don't use a named ATS — their careers page is an Algolia
InstantSearch UI, with jobs held in an Algolia index queried client-side via a public,
search-only API key. This adapter lists those postings straight off the Algolia REST API.

BoardRef shape: `token` = Algolia application id; `extra` = {"index": <index name>,
"api_key": <search-only key>, "host": <optional dsn host>, and optional field overrides:
title_field / id_field / url_field / location_field}. The app id + key + index are discovered
from the careers page at onboard time (see `ingestion/onboard.py`, Playwright network capture).

Records vary per site, so fields are detected heuristically (overridable via `extra`). Algolia
commonly emits one record per (job, location), so postings are deduped by job id and their
locations aggregated.
"""
from __future__ import annotations

from typing import Any

from resumaker.providers.sources.base import PostingStub
from resumaker.providers.sources.http import polite_post
from resumaker.providers.sources.ua import UA

_TITLE_FIELDS = ("name", "title", "jobTitle", "positionName", "position", "role")
_ID_FIELDS = ("jobId", "id", "objectID")
_URL_FIELDS = ("url", "jobUrl", "applyUrl", "absoluteUrl", "absolute_url", "applicationUrl")
_LOC_FIELDS = ("locationNames", "location", "locations", "city", "office", "offices")
_PER_PAGE = 100
_MAX_PAGES = 60            # safety cap: 60 * 100 = 6000 postings


def _pick(rec: dict, override: str, defaults: tuple[str, ...]) -> Any:
    """The value of `override` if set + present, else the first present-and-truthy default field."""
    if override and rec.get(override):
        return rec[override]
    for f in defaults:
        if rec.get(f):
            return rec[f]
    return None


def _loc_str(v: Any) -> str:
    """Flatten an Algolia location value (str / dict / list of either) to a readable string."""
    if not v:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("name") or v.get("city") or "").strip()
    if isinstance(v, list):
        return _loc_str(v[0]) if v else ""
    return str(v).strip()


class AlgoliaSource:
    source = "algolia"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        index = kwargs.get("index", "")
        api_key = kwargs.get("api_key", "")
        if not (token and index and api_key):
            raise ValueError("algolia adapter needs an app id (token) + index + api_key in extra")
        host = kwargs.get("host") or f"{token.lower()}-dsn.algolia.net"
        tf, idf = kwargs.get("title_field", ""), kwargs.get("id_field", "")
        uf, lf = kwargs.get("url_field", ""), kwargs.get("location_field", "")
        headers = {"x-algolia-application-id": token, "x-algolia-api-key": api_key,
                   "content-type": "application/json", "User-Agent": UA}
        url = f"https://{host}/1/indexes/{index}/query"

        by_id: dict[str, PostingStub] = {}
        locs: dict[str, list[str]] = {}
        page = 0
        while page < _MAX_PAGES:
            r = polite_post(url, headers,
                            json={"params": f"hitsPerPage={_PER_PAGE}&page={page}&query="})
            r.raise_for_status()
            data = r.json()
            for h in data.get("hits", []) or []:
                if not isinstance(h, dict):
                    continue
                ext_id = str(_pick(h, idf, _ID_FIELDS) or "").strip()
                if not ext_id:
                    continue
                loc = _loc_str(_pick(h, lf, _LOC_FIELDS))
                if ext_id in by_id:
                    if loc:
                        locs[ext_id].append(loc)
                    continue
                by_id[ext_id] = PostingStub(
                    source=self.source, external_id=ext_id,
                    url=str(_pick(h, uf, _URL_FIELDS) or ""),
                    title=str(_pick(h, tf, _TITLE_FIELDS) or "").strip(),
                    location=loc,
                )
                locs[ext_id] = [loc] if loc else []
            page += 1
            if page >= int(data.get("nbPages", 1) or 1):
                break

        for k, stub in by_id.items():
            uniq = list(dict.fromkeys(x for x in locs[k] if x))
            if len(uniq) > 1:
                stub.location = "; ".join(uniq[:3]) + (" +more" if len(uniq) > 3 else "")
        return list(by_id.values())
