"""Careers-page fingerprinter — the "eyes" for agentic onboarding.

Loads a careers URL in a headless browser and captures the signals an ATS adapter needs:
the JSON/API calls the page makes (Algolia, GraphQL, REST job feeds), embedded credentials
(Algolia app id + search key), JSON-LD JobPosting blocks, and any known ATS board links.
Returns a structured report.

Deterministic resolution (Algolia today) reads this directly; the agentic adapter-drafter is
handed the report as context, so it can author an adapter for a novel-but-publicly-fetchable
platform from the *actual* endpoints the page hits — without needing a browser inside the
locked sandbox. Bot-blocked sites that need a heavyweight stealth scraper still fall through.
"""
from __future__ import annotations

import contextlib
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# URLs worth capturing a response body for (job feeds / search backends), to keep the report small.
_API_HINT = re.compile(
    r"(algolia|graphql|/search|/jobs|/positions|requisition|recruit|workday|greenhouse"
    r"|lever|ashby|smartrecruiters|icims|eightfold|/api/|careers?)", re.I)
_MAX_CALLS = 25
_BODY_CHARS = 1500


def _summarize_json(text: str) -> Any:
    """A shallow, size-bounded shape of a JSON payload: keys + one sample element per list, so the
    agent sees the record structure (field names) without the whole response."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    def shape(v: Any, depth: int = 0) -> Any:
        if depth >= 3:
            return "…"
        if isinstance(v, dict):
            return {k: shape(v[k], depth + 1) for k in list(v)[:14]}
        if isinstance(v, list):
            return [shape(v[0], depth + 1), f"…+{len(v) - 1} more"] if len(v) > 1 else \
                   ([shape(v[0], depth + 1)] if v else [])
        if isinstance(v, str):
            return v[:80]
        return v

    return shape(obj)


def fingerprint(url: str, *, settle_ms: int = 5000) -> dict:
    """Load `url` headless and return a fingerprint report:
    {ok, final_url, title, board_links, algolia, json_ld, api_calls[], error}."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "playwright unavailable"}

    api_calls: list[dict] = []
    algolia: dict[str, str] = {}
    seen: set[str] = set()

    def _on_response(resp) -> None:  # noqa: ANN001
        try:
            u = resp.url
            key = u.split("?")[0]
            if key in seen or len(api_calls) >= _MAX_CALLS or not _API_HINT.search(u):
                return
            req = resp.request
            ct = (resp.headers or {}).get("content-type", "")
            is_json = "json" in ct
            if not is_json and "algolia" not in u:
                return
            seen.add(key)
            body = ""
            if is_json:
                with contextlib.suppress(Exception):
                    body = resp.text()[: _BODY_CHARS * 4]
            entry: dict = {"method": req.method, "url": key, "status": resp.status}
            if req.post_data:
                entry["request_body"] = req.post_data[:400]
            if body:
                entry["response_shape"] = _summarize_json(body)
            api_calls.append(entry)
            if ("algolia.net" in u or "algolianet.com" in u) and not algolia:
                q = parse_qs(urlsplit(u).query)
                app = (q.get("x-algolia-application-id") or [""])[0] \
                    or req.headers.get("x-algolia-application-id", "")
                akey = (q.get("x-algolia-api-key") or [""])[0] \
                    or req.headers.get("x-algolia-api-key", "")
                if app and akey:
                    algolia.update({"app_id": app, "api_key": akey,
                                    "host": urlsplit(u).hostname or ""})
        except Exception:  # noqa: BLE001 - never let a stray response break the capture
            pass

    report: dict = {"ok": False, "final_url": url, "title": "", "board_links": [],
                    "algolia": {}, "json_ld": [], "api_calls": []}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pg = b.new_page(user_agent=_UA)
            pg.on("response", _on_response)
            with contextlib.suppress(Exception):
                pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            with contextlib.suppress(Exception):
                pg.wait_for_timeout(settle_ms)
            html = ""
            with contextlib.suppress(Exception):
                html = pg.content()
                report["final_url"] = pg.url
                report["title"] = pg.title()
            b.close()
    except Exception as e:  # noqa: BLE001
        return {**report, "error": f"{type(e).__name__}: {e}"}

    report["algolia"] = algolia
    report["api_calls"] = api_calls
    report["board_links"] = _board_links(html)
    report["json_ld"] = _json_ld_jobs(html)
    report["ok"] = bool(algolia or api_calls or report["board_links"] or report["json_ld"])
    if algolia:
        # Try to name the index from the page config (Algolia sends it in the POST body otherwise).
        m = re.search(r'"algoliaIndexName"\s*:\s*"([^"]+)"', html)
        if m:
            report["algolia"]["index"] = m.group(1)
    return report


def _board_links(html: str) -> list[dict]:
    """Known ATS board links embedded in the page (greenhouse/lever/ashby/workday)."""
    pats = [
        ("greenhouse", r"(?:job-boards|boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)"),
        ("lever", r"jobs\.lever\.co/([\w-]+)"),
        ("ashby", r"jobs\.ashbyhq\.com/([\w-]+)"),
        ("workday", r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[\w-]+/)?([\w-]+)"),
    ]
    out: list[dict] = []
    for src, pat in pats:
        m = re.search(pat, html)
        if m:
            out.append({"source": src, "match": m.group(0)})
    return out


def _json_ld_jobs(html: str) -> list[dict]:
    """JSON-LD JobPosting blocks (schema.org) — some custom sites expose jobs this way."""
    out: list[dict] = []
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            obj = json.loads(m.group(1).strip())
            items = obj if isinstance(obj, list) else [obj]
            for it in items:
                if isinstance(it, dict) and "JobPosting" in str(it.get("@type", "")):
                    out.append({k: str(it.get(k, ""))[:80] for k in ("title", "url", "datePosted")})
    return out[:5]


if __name__ == "__main__":
    import sys
    print(json.dumps(fingerprint(sys.argv[1]), indent=2, default=str))
