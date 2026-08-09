"""Eval for Task 1.1 scraper. Discovers a live posting per ATS (postings expire,
so we probe board-list APIs for a working slug), then asserts scrape() returns
non-empty text with the right source_type. Run: `uv run python -m pocs.scrape_jd.eval`
"""
from __future__ import annotations

import httpx

from evals.harness import run_eval
from pocs.scrape_jd import scrape

UA = {"User-Agent": "Mozilla/5.0"}

GH_SLUGS = ["databricks", "stripe", "gitlab", "figma", "airbnb", "coinbase"]
LV_SLUGS = ["leverdemo", "netflix", "plaid", "ramp", "spotify", "brex"]
ASH_SLUGS = ["ramp", "notion", "linear", "openai", "vanta", "posthog"]


def _first(url_fn, slugs):
    for s in slugs:
        try:
            u = url_fn(s)
            if u:
                return u
        except Exception:  # noqa: BLE001
            continue
    return None


def gh_url(s):
    r = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
                  headers=UA, timeout=15)
    if r.status_code == 200 and r.json().get("jobs"):
        return f"https://boards.greenhouse.io/{s}/jobs/{r.json()['jobs'][0]['id']}"
    return None


def lv_url(s):
    r = httpx.get(f"https://api.lever.co/v0/postings/{s}?mode=json",
                  headers=UA, timeout=15)
    if r.status_code == 200 and isinstance(r.json(), list) and r.json():
        return f"https://jobs.lever.co/{s}/{r.json()[0]['id']}"
    return None


def ash_url(s):
    r = httpx.get(f"https://api.ashbyhq.com/posting-api/job-board/{s}",
                  headers=UA, timeout=15)
    if r.status_code == 200 and r.json().get("jobs"):
        return f"https://jobs.ashbyhq.com/{s}/{r.json()['jobs'][0]['id']}"
    return None


def build_cases():
    return [
        {"label": "greenhouse", "input": _first(gh_url, GH_SLUGS), "expect": "greenhouse"},
        {"label": "lever", "input": _first(lv_url, LV_SLUGS), "expect": "lever"},
        {"label": "ashby", "input": _first(ash_url, ASH_SLUGS), "expect": "ashby"},
        {"label": "playwright-fallback", "input": "https://example.com", "expect": "playwright"},
    ]


def _run(url):
    if not url:
        raise RuntimeError("no live posting discovered")
    return scrape(url)


def _score(jd, expect):
    if jd.source_type != expect:
        return False, f"source_type={jd.source_type} != {expect}"
    if not jd.ok or len(jd.raw_text) < 50:
        return False, f"ok={jd.ok} chars={len(jd.raw_text)}"
    return True, f"[{jd.source_type}] {len(jd.raw_text)} chars, title={jd.title[:30]!r}"


if __name__ == "__main__":
    run_eval("scrape_jd", build_cases(), _run, _score)
