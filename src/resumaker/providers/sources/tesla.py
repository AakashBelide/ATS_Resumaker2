"""Tesla careers adapter (`/cua-api/apps/careers/state`). Single-company (token ignored).

One GET returns Tesla's ENTIRE catalog plus a `lookup` dictionary that decodes the compact
per-listing codes (department / region / location). Tesla fronts this with Akamai Bot
Manager (TLS/JA3 fingerprinting), so - like Workday - we impersonate Chrome with curl_cffi.
A cold datacenter GET may still get an `_abck` 403 challenge, so this is verified from a
residential network; the response PARSER is fixture unit-tested. US filtering is client-side
on the decoded location (Tesla's "North America" region also spans CA/MX).
"""
from __future__ import annotations

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub

_log = get_logger("resumaker.sources.tesla")
_URL = "https://www.tesla.com/cua-api/apps/careers/state"


def _decode_location(listing: dict, locations: dict) -> str:
    """Resolve a listing's location code(s) to a display string via the lookup table."""
    raw = listing.get("l") or listing.get("location") or ""
    codes = raw if isinstance(raw, list) else [raw]
    parts = []
    for c in codes:
        key = str(c)
        val = locations.get(key)
        if isinstance(val, dict):                       # {"name": "...", "region": ...}
            val = val.get("name") or val.get("location") or key
        parts.append(str(val or key))
    return ", ".join(p for p in parts if p)


def parse_response(body: dict) -> list[PostingStub]:
    """Parse the careers/state payload into stubs. Defensive to key drift."""
    body = body or {}
    listings = body.get("listings") or body.get("jobs") or []
    lookup = body.get("lookup") or {}
    locations = lookup.get("locations") or lookup.get("location") or {}
    out: list[PostingStub] = []
    for j in listings:
        jid = str(j.get("id", "") or j.get("jobId", ""))
        out.append(PostingStub(
            source="tesla", external_id=jid,
            url=f"https://www.tesla.com/careers/search/job/{jid}",
            title=j.get("t", "") or j.get("title", ""),
            location=_decode_location(j, locations),
            updated_at=str(j.get("hT", "") or j.get("created", "")),
        ))
    return out


class TeslaSource:
    source = "tesla"

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        from curl_cffi import requests as cffi
        headers = {"Referer": "https://www.tesla.com/careers/search/",
                   "Accept": "application/json"}
        try:
            r = cffi.get(_URL, impersonate="chrome", timeout=30, headers=headers)
        except Exception as e:  # noqa: BLE001 - network blip / TLS block
            _log.warning("tesla state error", extra={"error": str(e)[:120]})
            return []
        if r.status_code != 200:
            _log.warning("tesla state non-200", extra={"status": r.status_code})
            return []
        return parse_response(r.json() or {})
