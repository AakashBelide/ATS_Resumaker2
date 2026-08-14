"""JD scraper: public ATS JSON APIs first, Playwright fallback.

Tiered by reliability: official public board APIs (Greenhouse/Lever/Ashby/Workday) return
clean structured text with no bot-protection risk; Playwright is the last-resort fallback
for arbitrary pages. Prefer official APIs; use the browser only within ToS.
"""
from __future__ import annotations

import html
import json
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
    source_type: str = ""          # greenhouse|lever|ashby|workday|playwright|http
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
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------- Greenhouse
def _greenhouse(url: str) -> RawJD | None:
    host = urlparse(url).netloc
    m = (re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)(?:/jobs/|.*gh_jid=)(\d+)", url)
         or re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", url))
    if m:
        company, job_id = m.group(1), m.group(2)
    else:
        # Custom-domain board (e.g. hubspot.com/careers/jobs/8119462?gh_jid=8119462): the URL carries
        # the greenhouse job id but no board token, so derive it from the registrable domain (the
        # greenhouse board token is almost always the company name). If the guess is wrong the API
        # 404s and we fall through.
        gh = re.search(r"[?&]gh_jid=(\d+)", url)
        if not gh:
            return None
        job_id = gh.group(1)
        labels = [x for x in host.split(".") if x not in ("www", "jobs", "careers")]
        company = labels[-2] if len(labels) >= 2 else labels[0]
    api = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}?content=true"
    r = httpx.get(api, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    if r.status_code != 200:
        return None
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
        (blk.get("text", "") + "\n" + _html_to_text(
            "".join(blk.get("content", "") if isinstance(blk.get("content"), str) else "")))
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
    m = re.search(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/]+)/job/(.+?)(?:\?|$)", url)
    if not m:
        return None
    tenant, wd, site, ext = m.group(1), m.group(2), m.group(3), m.group(4)
    ext = ext.removesuffix("/apply")     # some URLs end .../job/<ext>/apply -> CXS wants just <ext>
    host = f"{tenant}.{wd}.myworkdayjobs.com"
    cxs = f"https://{host}/wday/cxs/{tenant}/{site}/job/{ext}"
    # Workday is behind Akamai (TLS/JA3 fingerprinting) -> curl_cffi impersonation.
    from curl_cffi import requests as cffi
    r = cffi.get(cxs, impersonate="chrome", timeout=30, headers={"Accept": "application/json"})
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


# --------------------------------------------------------------- Oracle Recruiting Cloud (CE)
def _oracle_cloud(url: str) -> RawJD | None:
    """Oracle CE careers pages (jpmc/amex/citizens/staples/ford...) are JS-rendered - a plain
    HTTP GET returns an empty shell. The JD lives behind the same public JSON API the page calls:
    the requisition-detail resource, keyed by requisition Id (path form; siteNumber is rejected
    as a query param here). We stitch the HTML description/responsibilities/qualifications fields."""
    m = re.search(
        r"https?://([\w.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[^/]+/sites/([^/]+)/job/(\d+)",
        url)
    if not m:
        return None
    host, site, rid = m.group(1), m.group(2), m.group(3)
    api = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails/{rid}"
           f"?onlyData=true&expand=all")
    r = httpx.get(api, headers={"User-Agent": UA, "Accept": "application/json"},
                  timeout=25, follow_redirects=True)
    r.raise_for_status()
    j = r.json() or {}
    if not j.get("Title") and isinstance(j.get("items"), list) and j["items"]:
        j = j["items"][0]  # a few tenants wrap the row in items[]
    parts = [j.get(k, "") for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr",
                                    "ExternalQualificationsStr", "CorporateDescriptionStr")]
    return RawJD(
        raw_text=_html_to_text("\n".join(p for p in parts if p)),
        source_type="oracle_cloud", source_url=url,
        title=j.get("Title", ""), company=host.split(".", 1)[0],
        location=j.get("PrimaryLocation", ""),
        extra={"req_id": rid, "site": site},
    )


# --------------------------------------------------------------- Amazon / AWS
def _amazon(url: str) -> RawJD | None:
    """amazon.jobs detail pages are a JS-rendered SPA behind Akamai - a plain GET (or the `.json`
    variant) returns an empty shell / 406, so it used to fall to the Playwright path. The JD lives
    behind the same public `search.json` API the ingestion adapter already uses: query by the job id
    and stitch description + basic/preferred qualifications. Covers Amazon and AWS roles."""
    m = re.search(r"amazon\.jobs/[a-z-]+/jobs/(\d+)", url)
    if not m:
        return None
    job_id = m.group(1)
    api = "https://www.amazon.jobs/en/search.json"
    r = httpx.get(api, params={"base_query": job_id, "result_limit": "10", "sort": "relevant"},
                  headers={"User-Agent": UA, "Accept": "application/json"},
                  timeout=25, follow_redirects=True)
    r.raise_for_status()
    jobs = (r.json() or {}).get("jobs", []) or []
    # base_query is a text search, so confirm we matched the exact id (id_icims/id) before trusting it.
    job = next((j for j in jobs if str(j.get("id_icims") or j.get("id")) == job_id), None)
    if job is None:
        return None
    parts = [job.get(k, "") for k in ("description", "basic_qualifications", "preferred_qualifications")]
    return RawJD(
        raw_text=_html_to_text("\n\n".join(p for p in parts if p)),
        source_type="amazon", source_url=url,
        title=job.get("title", ""), company=job.get("company_name", "") or "Amazon",
        location=job.get("normalized_location", "") or job.get("location", ""),
        extra={"job_id": job_id},
    )


# --------------------------------------------------------------- Rippling ATS
def _rippling(url: str) -> RawJD | None:
    """Rippling-hosted boards (ats.rippling.com/<slug>/jobs/<uuid>). The public board API returns
    the full JD by uuid."""
    m = re.search(r"rippling\.com/([\w-]+)/jobs/([0-9a-f-]{36})", url)
    if not m:
        return None
    slug, uuid = m.group(1), m.group(2)
    api = f"https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs/{uuid}"
    r = httpx.get(api, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=25,
                  follow_redirects=True)
    if r.status_code != 200:
        return None
    j = r.json() or {}
    locs = j.get("workLocations") or []
    return RawJD(
        raw_text=_html_to_text(j.get("description", "")),
        source_type="rippling", source_url=url,
        title=j.get("name", ""), company=slug,
        location=", ".join(loc.get("label", "") for loc in locs if loc.get("label")),
        extra={"uuid": uuid},
    )


# --------------------------------------------------------------- Eightfold
def _eightfold(url: str) -> RawJD | None:
    """Eightfold career sites (app.eightfold.ai and white-label hosts like explore.jobs.<co>.net).
    The position-detail API needs a `domain` param that isn't in the URL, so we try a few candidates
    derived from the host and self-validate on a non-empty job_description."""
    m = re.search(r"/careers/job/(\d{6,})", url)
    if not m:
        return None
    host = urlparse(url).netloc
    job_id = m.group(1)
    skip = {"explore", "jobs", "careers", "app", "www", "eightfold", "ai", "com", "net", "io", "co"}
    labels = [x for x in host.split(".") if x not in skip]
    cands = [f"{x}.com" for x in labels] + [f"{x}.net" for x in labels]
    cands.append(".".join(host.split(".")[-2:]))
    for domain in dict.fromkeys(cands):     # de-dup, keep order
        try:
            r = httpx.get(f"https://{host}/api/apply/v2/jobs/{job_id}", params={"domain": domain},
                          headers={"User-Agent": UA, "Accept": "application/json"}, timeout=20,
                          follow_redirects=True)
            if r.status_code != 200:
                continue
            j = r.json() or {}
            desc = j.get("job_description") or j.get("description") or ""
            if desc:
                loc = j.get("location") or (j.get("locations") or [""])[0]
                return RawJD(raw_text=_html_to_text(desc), source_type="eightfold", source_url=url,
                             title=j.get("name", ""), company=labels[0] if labels else host,
                             location=loc if isinstance(loc, str) else "", extra={"job_id": job_id})
        except Exception:  # noqa: BLE001 - try the next candidate domain
            continue
    return None


# --------------------------------------------------------------- Generic JSON-LD (schema.org)
def _jsonld(url: str) -> RawJD | None:
    """Last structured-data resort before Playwright: many careers pages (Radancy/Takeda, Dassault,
    iCIMS, some Avature) render server-side HTML with a schema.org JobPosting in a <script
    type="application/ld+json">. Parse it - full JD, no browser needed. Runs on any URL, so it's the
    final API handler; returns None (=> Playwright) when no JobPosting is present."""
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=25, follow_redirects=True)
        if r.status_code != 200:
            return None
    except Exception:  # noqa: BLE001
        return None
    soup = BeautifulSoup(r.text, "lxml")

    def _walk(node: object) -> dict | None:
        if isinstance(node, dict):
            if node.get("@type") == "JobPosting" or "JobPosting" in (node.get("@type") or []):
                return node
            for v in node.values():
                hit = _walk(v)
                if hit:
                    return hit
        elif isinstance(node, list):
            for v in node:
                hit = _walk(v)
                if hit:
                    return hit
        return None

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        job = _walk(data)
        if not job:
            continue
        desc = _html_to_text(job.get("description", ""))
        if not desc:
            continue
        org = job.get("hiringOrganization") or {}
        loc = job.get("jobLocation") or {}
        loc = loc[0] if isinstance(loc, list) and loc else loc
        addr = (loc.get("address") if isinstance(loc, dict) else {}) or {}
        city = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
        region = addr.get("addressRegion", "") if isinstance(addr, dict) else ""
        return RawJD(
            raw_text=desc, source_type="jsonld", source_url=url,
            title=job.get("title", ""),
            company=(org.get("name", "") if isinstance(org, dict) else "") or urlparse(url).netloc,
            location=", ".join(p for p in (city, region) if p),
        )
    return None


# --------------------------------------------------------------- Playwright fallback
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
    return RawJD(raw_text=_html_to_text(content), source_type="playwright", source_url=url)


# Specific board handlers first; `_jsonld` is the generic structured-data fallback, tried last
# before Playwright (it runs on any URL, so it must not preempt a dedicated handler).
_API_HANDLERS = [_greenhouse, _lever, _ashby, _workday, _oracle_cloud, _amazon,
                 _rippling, _eightfold, _jsonld]


def scrape(url: str) -> RawJD:
    """Scrape a JD from a URL. Tries public ATS APIs, falls back to Playwright."""
    for handler in _API_HANDLERS:
        try:
            result = handler(url)
        except Exception as e:  # noqa: BLE001 - API failed, try the next handler/fallback
            _ = RawJD(ok=False, error=f"{handler.__name__}: {e}", source_url=url)
            continue
        if result is not None and result.raw_text:
            return result
    try:
        return _playwright(url)
    except Exception as e:  # noqa: BLE001
        return RawJD(ok=False, error=f"playwright: {e}", source_url=url)
