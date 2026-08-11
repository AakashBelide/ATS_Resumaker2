#!/usr/bin/env python3
"""fetch — pull a careers/ATS page so the agent can spot the board link in it.

Standalone (httpx only). Honors HTTP(S)_PROXY, so inside the sandbox this can only reach
allow-listed hosts. Prints the HTTP status, the final URL (after redirects), any ATS board
links found (greenhouse/lever/ashby/workday), and a trimmed slice of text — enough for the
agent to reason about without dumping a whole page.

Usage:  fetch.py <url> [--max-chars 4000]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

BOARD_PATTERNS = [
    ("greenhouse", r"(?:job-boards|boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)"),
    ("lever", r"jobs\.lever\.co/([\w-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w-]+)"),
    ("workday", r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[\w-]+/)?([\w-]+)"),
]


def find_boards(html: str) -> list[dict]:
    found: list[dict] = []
    for source, pat in BOARD_PATTERNS:
        for m in re.finditer(pat, html):
            if source == "workday":
                tenant, wd, site = m.group(1), m.group(2), m.group(3)
                ref = {"source": "workday", "token": tenant,
                       "host": f"{tenant}.{wd}.myworkdayjobs.com", "site": site}
            else:
                ref = {"source": source, "token": m.group(1)}
            if ref not in found:
                found.append(ref)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--max-chars", type=int, default=4000)
    a = ap.parse_args()

    out: dict = {"url": a.url}
    try:
        with httpx.Client(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as c:
            r = c.get(a.url)
        html = r.text or ""
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        out.update({
            "status": r.status_code,
            "final_url": str(r.url),
            "boards_found": find_boards(html),
            "text_excerpt": text[:a.max_chars],
        })
    except Exception as e:  # noqa: BLE001
        out.update({"status": 0, "error": f"{type(e).__name__}: {e}", "boards_found": []})
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
