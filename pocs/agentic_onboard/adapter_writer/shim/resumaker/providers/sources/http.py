"""Shim of the real `http` helper. `polite_get` returns an httpx response (which exposes
.status_code/.json()/.text — the same surface adapters use). Inside the sandbox this honors
HTTP(S)_PROXY, so a draft adapter's live check still goes through the egress allow-list."""
from __future__ import annotations

import httpx

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def polite_get(url: str, headers: dict | None = None, timeout: int = 25) -> httpx.Response:
    h = {"User-Agent": _UA, **(headers or {})}
    return httpx.get(url, headers=h, timeout=timeout, follow_redirects=True)
