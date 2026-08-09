"""Eightfold PCSX adapter (`app.eightfold.ai/api/pcsx/search`). Covers Qualcomm and other
Eightfold tenants on the PCSX (not SmartApply) stack.

Distinct from `eightfold.py`: those tenants serve `/api/apply/v2/jobs` (a `positions` array +
`count`); PCSX tenants 403 that path and instead serve `/api/pcsx/search` returning
`data.positions[]` + `data.count`. A board is its Eightfold `domain`, carried in extra:
    BoardRef(source="pcsx", token="qualcomm", extra={"domain": "qualcomm.com"})

Bot protection: Cloudflare fronts app.eightfold.ai and 403s cold datacenter GETs - the API
only answers once a browser holds `cf_clearance`. We impersonate Chrome with curl_cffi (best
headless-free shot at the TLS/fingerprint gate); if it still 403s, this board needs the
browser/residential tier. The response PARSER is fixture unit-tested regardless. US filtering
is client-side on `standardizedLocations` (normalized, US entries end in ", US").
"""
from __future__ import annotations

from datetime import UTC, datetime

from resumaker.observability.logging import get_logger
from resumaker.providers.sources.base import PostingStub

_log = get_logger("resumaker.sources.pcsx")
_BASE = "https://app.eightfold.ai/api/pcsx/search"
_PAGE = 10            # PCSX returns 10/page regardless of `num`
_MAX_PAGES = 12


def parse_response(body: dict) -> tuple[list[PostingStub], int]:
    """Parse a PCSX search response into (stubs, total). Defensive to shape drift."""
    data = (body or {}).get("data") or {}
    positions = data.get("positions") or []
    total = int(data.get("count") or 0)
    out: list[PostingStub] = []
    for p in positions:
        pid = str(p.get("id", ""))
        std = p.get("standardizedLocations") or []
        locs = p.get("locations") or []
        loc = (std[0] if std else locs[0] if locs else "") or ""
        posted = p.get("postedTs") or p.get("creationTs")
        updated = datetime.fromtimestamp(posted, UTC).isoformat() \
            if isinstance(posted, int | float) else ""
        rel = p.get("positionUrl") or f"/careers/job/{pid}"
        out.append(PostingStub(
            source="pcsx", external_id=pid,
            url=f"https://app.eightfold.ai{rel}",
            title=p.get("name", ""), location=str(loc), updated_at=updated))
    return out, total


class PcsxSource:
    source = "pcsx"

    def list_postings(self, token: str, *, domain: str = "", **kwargs: str) -> list[PostingStub]:
        if not domain:
            raise ValueError("pcsx board needs extra={'domain': ...}")
        from curl_cffi import requests as cffi
        headers = {"Accept": "application/json",
                   "Referer": f"https://app.eightfold.ai/careers?domain={domain}"}
        out: list[PostingStub] = []
        start = 0
        for _ in range(_MAX_PAGES):
            url = (f"{_BASE}?domain={domain}&query=&location=&start={start}"
                   f"&num={_PAGE}&sort_by=relevance")
            try:
                r = cffi.get(url, impersonate="chrome", timeout=30, headers=headers)
            except Exception as e:  # noqa: BLE001 - network blip / TLS block
                _log.warning("pcsx get error", extra={"domain": domain, "error": str(e)[:120]})
                break
            if r.status_code != 200:                   # 403 => Cloudflare gate (needs browser)
                _log.warning("pcsx non-200 (likely Cloudflare)",
                             extra={"domain": domain, "status": r.status_code})
                break
            stubs, total = parse_response(r.json() or {})
            out.extend(stubs)
            start += _PAGE
            if not stubs or start >= total:
                break
        return out
