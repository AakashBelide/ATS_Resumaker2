#!/usr/bin/env python3
"""ats_probe — does this (source, token) resolve to a real board with live postings?

The onboarding agent calls this to VERIFY a candidate board before returning it. Standalone
(httpx only, no app source) so it runs self-contained inside the sandbox. Honors HTTP(S)_PROXY
from the environment, so inside the box every call still goes through the egress allow-list.

Usage:
  ats_probe.py greenhouse stripe
  ats_probe.py lever brex
  ats_probe.py ashby openai
  ats_probe.py workday <tenant> --host <tenant>.wd1.myworkdayjobs.com --site <site>
  ats_probe.py amazon ""          # single-company custom board (token unused)
  ats_probe.py microsoft ""       # single-company custom board (token unused)

Prints one JSON line: {source, token, count, ok, board_name?, sample:[titles], error?}
Exit 0 always (the agent reads the JSON); `ok` is the truth signal (count > 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlencode

import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _client() -> httpx.Client:
    # trust_env=True (default) => picks up HTTP(S)_PROXY inside the sandbox.
    return httpx.Client(headers={"User-Agent": UA}, timeout=20, follow_redirects=True)


def greenhouse(token: str) -> dict:
    with _client() as c:
        jobs = c.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
        board = c.get(f"https://boards-api.greenhouse.io/v1/boards/{token}")
    js = jobs.json().get("jobs", []) if jobs.status_code == 200 else []
    name = board.json().get("name", "") if board.status_code == 200 else ""
    return {"count": len(js), "board_name": name, "sample": [j.get("title", "") for j in js[:5]]}


def lever(token: str) -> dict:
    with _client() as c:
        r = c.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
    js = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
    return {"count": len(js), "sample": [j.get("text", "") for j in js[:5]]}


def ashby(token: str) -> dict:
    with _client() as c:
        r = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}",
                  params={"includeCompensation": "true"})
    js = r.json().get("jobs", []) if r.status_code == 200 else []
    return {"count": len(js), "sample": [j.get("title", "") for j in js[:5]]}


def workday(token: str, host: str, site: str) -> dict:
    # Best-effort: many Workday tenants sit behind Akamai and need TLS impersonation
    # (curl_cffi) which we don't ship in the minimal box — a 403 here is inconclusive,
    # not a "no". The agent should treat a found *.myworkdayjobs.com host as promising.
    url = f"https://{host}/wday/cxs/{token}/{site}/jobs"
    with _client() as c:
        r = c.post(url, json={"limit": 20, "offset": 0, "searchText": ""},
                   headers={"Accept": "application/json", "Content-Type": "application/json"})
    if r.status_code != 200:
        return {"count": 0, "sample": [], "error": f"workday http {r.status_code} (may need curl_cffi)"}
    js = r.json().get("jobPostings", [])
    return {"count": len(js), "sample": [j.get("title", "") for j in js[:5]]}


def amazon(team: str = "") -> dict:
    # Single-company custom board (also covers AWS via team=AWS). Public JSON, no auth.
    params = [("normalized_country_code[]", "USA"), ("result_limit", 20),
              ("offset", 0), ("sort", "recent"), ("base_query", "")]
    if team:
        params.append(("team", team))
    with _client() as c:
        r = c.get(f"https://www.amazon.jobs/en/search.json?{urlencode(params)}")
    if r.status_code != 200:
        return {"count": 0, "sample": [], "error": f"amazon http {r.status_code}"}
    body = r.json() or {}
    jobs = body.get("jobs", []) or []
    return {"count": int(body.get("hits", len(jobs)) or 0),
            "board_name": "Amazon", "sample": [j.get("title", "") for j in jobs[:5]]}


def microsoft(_token: str = "") -> dict:
    # Single-company custom board (GCS API). Azure Front Door may 4xx some datacenter IPs;
    # from a residential egress it returns clean JSON.
    q = urlencode({"q": "", "lc": "United States", "l": "en_us", "pg": 1,
                   "pgSz": 20, "o": "Recent", "flt": "true"})
    with _client() as c:
        r = c.get(f"https://gcsservices.careers.microsoft.com/search/api/v1/search?{q}",
                  headers={"Referer": "https://careers.microsoft.com/"})
    if r.status_code != 200:
        return {"count": 0, "sample": [], "error": f"microsoft http {r.status_code} (Azure edge may block non-residential IPs)"}
    res = ((r.json() or {}).get("operationResult") or {}).get("result") or {}
    jobs = res.get("jobs") or []
    return {"count": int(res.get("totalJobs") or res.get("total") or 0),
            "board_name": "Microsoft", "sample": [j.get("title", "") for j in jobs[:5]]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["greenhouse", "lever", "ashby", "workday",
                                       "amazon", "microsoft"])
    ap.add_argument("token", nargs="?", default="")
    ap.add_argument("--host", default="")
    ap.add_argument("--site", default="")
    ap.add_argument("--team", default="")
    a = ap.parse_args()

    out: dict = {"source": a.source, "token": a.token}
    try:
        if a.source == "greenhouse":
            out.update(greenhouse(a.token))
        elif a.source == "lever":
            out.update(lever(a.token))
        elif a.source == "ashby":
            out.update(ashby(a.token))
        elif a.source == "amazon":
            out.update(amazon(a.team))
        elif a.source == "microsoft":
            out.update(microsoft(a.token))
        else:
            out.update(workday(a.token, a.host, a.site))
    except Exception as e:  # noqa: BLE001 - report, don't crash the agent
        out.update({"count": 0, "sample": [], "error": f"{type(e).__name__}: {e}"})
    out["ok"] = out.get("count", 0) > 0
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
