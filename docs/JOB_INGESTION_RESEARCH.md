# Job Ingestion at Scale — Research & Design Notes

Practical guidance for the watchlist ingestion subsystem (RI), from a deep-research pass
(Aug 2026) that verified all four ATS behaviors against live endpoints. This is the
"why" behind the anti-blocking + freshness design in `src/resumaker/ingestion/` and
`src/resumaker/providers/sources/`.

## TL;DR for our scale (50–500 companies)
- **Not realistically at risk of blocks.** One home/residential IP polling clean ATS JSON
  endpoints once or twice a day is a few hundred–few thousand requests/day — normal traffic.
  No proxies, no JA3/TLS evasion needed for Greenhouse/Lever/Ashby/Workday CxS.
- **Serious aggregators (hiring.cafe, Simplify, LinkedIn "Limited Listings", Indeed) do
  exactly this** — ingest the official public JSON/XML feeds; only fall back to headless/
  stealth scraping for career sites with no clean endpoint.
- **Prefer the front-end's own API**, not the rendered career page. Hitting the JSON the
  career-site SPA already calls is indistinguishable from normal traffic and sidesteps bot
  defenses. Scraping the branded HTML is *more* likely to be blocked.

## Anti-blocking (what we implemented)
- **Pacing:** ~1 req/s per host, low concurrency, jitter between companies + pages
  (Scrapy AutoThrottle is the reference). Lever's robots.txt: `Crawl-delay: 1` (welcomes it).
- **Descriptive User-Agent** (`resumaker/1.0 (personal job watchlist)`) for the clean JSON
  boards — honest and polite; all four return 200 to a plain UA.
- **429/403 → exponential backoff with jitter, honoring `Retry-After`**; on repeated 403
  (hard bot block) stop and reassess rather than hammer. Implemented in the Workday adapter.
- **Conditional GET where supported (biggest "don't re-fetch" win):** Greenhouse supports
  `ETag`/`If-None-Match` → `304 Not Modified` (+ gzip). We store the ETag and skip unchanged
  boards. Ashby has a weak ETag (`max-age=60`); Lever's is undocumented; Workday CxS is
  `no-store` (no conditional support).
- **TLS/JA3 impersonation (`curl_cffi`) only for Workday** (Akamai/Cloudflare-fronted). The
  CxS *API* route isn't challenged, but impersonation keeps it robust.
- **Proxies:** not needed at our scale; only if a single IP starts getting blocked or we add
  bot-protected custom sites. Residential > datacenter if ever required.

## Freshness / new-vs-old detection (verified fields)
| ATS | Endpoint | Stable ID | New-posting date | Edit detection | Default sort |
|---|---|---|---|---|---|
| Greenhouse | `GET /v1/boards/{token}/jobs[?content=true]` | `id` (+`internal_job_id`) | `first_published` (job detail); `updated_at`=last-modified | `updated_at` or hash of `content` | list order |
| Lever | `GET /v0/postings/{site}?mode=json` | `id` (UUID) | `createdAt` (epoch ms, undocumented) | hash of `descriptionPlain`+`text` | not newest-first (sort client-side) |
| Ashby | `GET /posting-api/job-board/{org}` | `id` (UUID) | `publishedAt` (ISO; **not** `publishedDate`) | hash; `updatedAt` often null | gate on `isListed===true` |
| Workday | `POST /wday/cxs/{tenant}/{site}/jobs` | req-id `bulletFields[0]` (e.g. `JR…`) + `externalPath` | `postedOn` (relative string); `startDate` on detail | hash of detail `jobDescription` | **newest-first** (verified) |

- **Dedup key:** `{source}:{external_id}` (our `jobs` UNIQUE(source, external_id)).
- **New vs edited:** `content_hash` over listing fields flags edits/re-posts; only new/changed
  rows are surfaced. Greenhouse ETag skips unchanged boards entirely.
- **Workday paging:** CxS has no sort param but is already date-descending; page in steps of
  20 (its anonymous cap) and stop early — for daily polling only the first pages matter.
  `limit>20` returns empty; large boards cap ~10k results (facet-slice to go deeper).

## Free / small-scale architecture (what we run)
- **Stack:** `httpx` (HTTP/2, pooling) for JSON APIs + `curl_cffi` for Workday; **SQLite** for
  state (`jobs` + a content-addressed cache for ETags); APScheduler for cadence.
- **Cadence:** Greenhouse/Lever/Ashby hourly (no bot protection); **Workday daily** (throttles).
  500 companies × 2 runs/day ≈ 1–3k requests/day — comfortable on one box, one IP.
- **Stealth tools:** *only* for future bot-protected custom sites. Recommendation: **Scrapling**
  (BSD-3, free; tiered `Fetcher`→`StealthyFetcher`→`DynamicFetcher`, self-healing selectors,
  built-in proxy rotator). **Not Firecrawl** (free tier ~1k pages/mo; self-host is AGPL-3.0 and
  puts the anti-bot infra back on you). `crawl4ai` if LLM-ready markdown is wanted.

## Legal / ToS (call-outs)
- CFAA risk for scraping **public, unauthenticated** data is low (*hiQ v. LinkedIn* 9th Cir.
  2022; *Van Buren* 2021; *Meta v. Bright Data* 2024 for logged-out data).
- Residual risk is **contract/ToS**, strongest when you click-through/agree or log in.
- `robots.txt` is voluntary (RFC 9309) but respect it — all four ATS hosts allow the API path.
- Stay in the safe zone: **public + not logged in + no bypassing technical blocks + no wholesale
  re-publication of full JDs + respect robots.txt & rate limits.** Our personal, low-volume,
  public-JSON, facts-only watchlist sits squarely there.

## Deferred-7 outcome (Aug 2026 deep-dive, per-company)

The "custom career site" tail was researched against live endpoints. Verdicts:

| Company | Source adapter | Endpoint | Bot gate | Headless-free? |
|---|---|---|---|---|
| Google | `google` (new) | SSR `about/careers/applications/jobs/results` `ds:1` blob | none | **yes — verified 200 from datacenter** |
| Atlassian | `jibe` (reuse) | `join.atlassian.com/api/jobs` | none | **yes — verified 200 from datacenter** |
| Tesla | `tesla` (new) | `/cua-api/apps/careers/state` (whole catalog + `lookup`) | Akamai `_abck` | curl_cffi Chrome-impersonation; else browser cookies |
| Qualcomm | `pcsx` (new) | `app.eightfold.ai/api/pcsx/search` (NOT `/apply/v2`) | Cloudflare | curl_cffi best-effort; may need `cf_clearance` |
| FedEx | `paradox` (new) | `careers.fedex.com/api/get-jobs` (Paradox, NOT Phenom) | Akamai-style WAF | GET `/jobs` first for the `ct` cookie, then POST |
| Meta | `meta` (new) | `metacareers.com/graphql` `CareersJobSearchResultsDataQuery` | FB edge (bare req → 400; rapid → IP block) | rotating `doc_id` scraped from JS bundle + `lsd` + full browser headers; residential IP |
| Wayfair | `wayfair` (new) | `wayfair.com/.../job_search_data` XHR (Avature backend) | **PerimeterX/HUMAN** | **yes, via curl_cffi** — plain httpx 429s, but Chrome TLS-impersonation + a warmed cookie jar (GET the careers page first) clears the PX fingerprint gate and the XHR returns all 329 US jobs. Live-verified. |

Two more tail companies, both **clean** (200 from datacenter, no bot protection): **IBM** —
bespoke Elasticsearch POST API (`www-api.ibm.com/search/api/v2`, `field_keyword_05` = country
facet), new `ibm` adapter, live-verified (140 US). **Suffolk** — iCIMS *classic* HTML portal
(`careers-suffolkconstruction.icims.com`, no JSON on this tenant), new `icims` adapter that
parses the `in_iframe=1` rows, live-verified (283 postings). Neither exposes a posting date in
the list, so `first_seen` synthesizes freshness.

Takeaways that generalize: (1) the endpoint a compiled spec *assumes* is often wrong — always
confirm live (Google's v3 REST is dead; Qualcomm is PCSX not SmartApply; FedEx is Paradox not
Phenom). (2) "Bot-protected" ≠ "impossible": Akamai/Cloudflare TLS gates often yield to
`curl_cffi` impersonation or a one-time cookie warmup - even PerimeterX on Wayfair yielded to
curl_cffi Chrome-TLS + a warmed cookie jar (no browser needed after all). (3) A datacenter IP
is the real blocker for
Meta/Tesla/Qualcomm/FedEx — the same adapters are expected to pass from the user's residential
network, which is where they're verified. Parsers for all are fixture unit-tested regardless.

_Sources: Greenhouse/Lever/Ashby/Workday API docs; Scrapy AutoThrottle; MDN conditional
requests & 429/Retry-After; curl_cffi; Scrapling/crawl4ai/Firecrawl; hiQ/Van Buren/Bright
Data; RFC 9309. (Full citations in the research transcript.)_
