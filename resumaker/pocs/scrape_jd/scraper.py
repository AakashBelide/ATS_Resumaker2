"""JD scraper: public ATS JSON APIs first, Playwright fallback.

Stealth/extraction options to evaluate for bot-protected pages (Task 1.1 follow-up),
none wired in yet:
  - Firecrawl   (hosted API + self-hostable; JS render; returns clean markdown; free tier)
  - Scrapling   (adaptive Python scraper, stealth fetch)
  - CloakBrowser (anti-bot browser)
Prefer official public APIs; use stealth only within ToS / on our own Phase-3 test ATS.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class RawJD:
    raw_text: str = ""
    source_type: str = ""          # greenhouse|lever|ashby|playwright|http
    source_url: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    ok: bool = True
    error: str = ""
    extra: dict = field(default_factory=dict)


def _html_to_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(html.unescape(raw_html), "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    # collapse excess blank lines
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------- Greenhouse
def _greenhouse(url: str) -> RawJD | None:
    # boards.greenhouse.io/{co}/jobs/{id}  |  job-boards.greenhouse.io/{co}/jobs/{id}
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)(?:/jobs/|.*gh_jid=)(\d+)", url)
    host = urlparse(url).netloc
    if "greenhouse" not in host and "greenhouse" not in url:
        return None
    if not m:
        m = re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", url)
    if not m:
        return None
    company, job_id = m.group(1), m.group(2)
    api = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}?content=true"
    r = httpx.get(api, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    r.raise_for_status()
    j = r.json()
    return RawJD(
        raw_text=_html_to_text(j.get("content", "")),
        source_type="greenhouse", source_url=url,
        title=j.get("title", ""), company=company,
        location=(j.get("location") or {}).get("name", ""),
        extra={"job_id": job_id},
    )


# --------------------------------------------------------------- Lever
def _lever(url: str) -> RawJD | None:
    m = re.search(r"lever\.co/([\w-]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    company, post_id = m.group(1), m.group(2)
    api = f"https://api.lever.co/v0/postings/{company}/{post_id}?mode=json"
    r = httpx.get(api, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    r.raise_for_status()
    j = r.json()
    body = _html_to_text(j.get("description", "") or j.get("descriptionPlain", ""))
    lists = "\n".join(
        (blk.get("text", "") + "\n" + _html_to_text("".join(blk.get("content", "") if isinstance(blk.get("content"), str) else "")))
        for blk in j.get("lists", []) or []
    )
    return RawJD(
        raw_text=(body + "\n" + lists).strip(),
        source_type="lever", source_url=url,
        title=j.get("text", ""), company=company,
        location=(j.get("categories") or {}).get("location", ""),
        extra={"post_id": post_id},
    )


# --------------------------------------------------------------- Ashby
def _ashby(url: str) -> RawJD | None:
    m = re.search(r"ashbyhq\.com/([\w-]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    company, job_id = m.group(1), m.group(2)
    api = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
    r = httpx.get(api, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    r.raise_for_status()
    postings = r.json().get("jobs", [])
    match = next((p for p in postings if p.get("id") == job_id), None)
    if not match:
        return None
    return RawJD(
        raw_text=_html_to_text(match.get("descriptionHtml", "")
                               or match.get("descriptionPlain", "")),
        source_type="ashby", source_url=url,
        title=match.get("title", ""), company=company,
        location=match.get("location", ""),
        extra={"job_id": job_id},
    )


# --------------------------------------------------------------- Workday (CXS JSON)
def _workday(url: str) -> RawJD | None:
    # https://{tenant}.wdN.myworkdayjobs.com/{site}/job/{externalPath}
    m = re.search(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/]+)/job/(.+?)(?:\?|$)", url)
    if not m:
        return None
    tenant, wd, site, ext = m.group(1), m.group(2), m.group(3), m.group(4)
    host = f"{tenant}.{wd}.myworkdayjobs.com"
    cxs = f"https://{host}/wday/cxs/{tenant}/{site}/job/{ext}"
    # Workday is behind Akamai (TLS/JA3 fingerprinting) -> curl_cffi impersonation.
    from curl_cffi import requests as cffi
    r = cffi.get(cxs, impersonate="chrome", timeout=30,
                 headers={"Accept": "application/json"})
    if r.status_code != 200:
        return None
    info = (r.json() or {}).get("jobPostingInfo", {})
    if not info:
        return None
    return RawJD(
        raw_text=_html_to_text(info.get("jobDescription", "")),
        source_type="workday", source_url=url,
        title=info.get("title", ""), company=tenant,
        location=info.get("location", ""),
        extra={"job_req_id": info.get("jobReqId", "")},
    )


# --------------------------------------------------------------- Playwright
def _playwright(url: str) -> RawJD:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)  # let JS settle
            content = page.content()
        finally:
            browser.close()
    return RawJD(raw_text=_html_to_text(content), source_type="playwright",
                 source_url=url)


_API_HANDLERS = [_greenhouse, _lever, _ashby, _workday]


def scrape(url: str) -> RawJD:
    """Scrape a JD from a URL. Tries public ATS APIs, falls back to Playwright."""
    for handler in _API_HANDLERS:
        try:
            result = handler(url)
        except Exception as e:  # noqa: BLE001 - API failed, fall through
            result = RawJD(ok=False, error=f"{handler.__name__}: {e}",
                           source_url=url)
            if result.error:
                # remember the error but keep trying other handlers/fallback
                continue
        if result is not None and result.raw_text:
            return result
    # fallback
    try:
        return _playwright(url)
    except Exception as e:  # noqa: BLE001
        return RawJD(ok=False, error=f"playwright: {e}", source_url=url)


if __name__ == "__main__":
    import sys
    jd = scrape(sys.argv[1])
    print(f"[{jd.source_type}] ok={jd.ok} title={jd.title!r} company={jd.company!r} "
          f"loc={jd.location!r} chars={len(jd.raw_text)}")
    if jd.error:
        print("ERROR:", jd.error)
    print("-" * 60)
    print(jd.raw_text[:1200])
