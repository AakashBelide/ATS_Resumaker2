"""Polite HTTP GET for the clean JSON board APIs (Greenhouse/Lever/Ashby).

Centralizes the rate-limit etiquette the research prescribes: on 429/503 we back off with
exponential delay + jitter, honoring a `Retry-After` header when present, before giving up.
Returns the final response (including 304/4xx) so callers handle status themselves - e.g.
Greenhouse inspects 304 and the ETag.
"""
from __future__ import annotations

import random
import time

import httpx

from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.sources.http")
_RETRY_STATUS = {429, 503}


def _with_backoff(send, url: str, *, attempts: int) -> httpx.Response:
    r = None
    for attempt in range(attempts):
        r = send()
        if r.status_code not in _RETRY_STATUS:
            return r
        retry_after = r.headers.get("Retry-After")
        delay = (float(retry_after) if (retry_after or "").isdigit()
                 else 1.5 * (attempt + 1) + random.uniform(0, 0.75))
        _log.warning("board throttled; backing off",
                     extra={"url": url, "status": r.status_code, "delay": round(delay, 2)})
        time.sleep(delay)
    assert r is not None
    return r  # exhausted retries - caller decides what to do with the status


def polite_get(url: str, headers: dict[str, str], *, timeout: float = 20.0,
               attempts: int = 3) -> httpx.Response:
    return _with_backoff(
        lambda: httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True),
        url, attempts=attempts)


def polite_post(url: str, headers: dict[str, str], *, json=None, content=None,
                timeout: float = 20.0, attempts: int = 3) -> httpx.Response:
    return _with_backoff(
        lambda: httpx.post(url, headers=headers, json=json, content=content,
                           timeout=timeout, follow_redirects=True),
        url, attempts=attempts)
