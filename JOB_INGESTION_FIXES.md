# Job Ingestion — Zero-Jobs Investigation & Fix Report

**Date:** 2026-08-09
**Scope:** 8 onboarded companies that show 0 jobs (absent from the tracker/report company dropdown).
**Method:** Standalone verification (no project code or data modified) — direct calls to each live ATS via `curl`, plus running the project's real filter functions (`is_tech_role`, `is_us_location`) against the fetched data. All commands were run outside the repo (scratchpad).

## Context — how a company ends up with 0 jobs

- The tracker/report **company dropdown only lists companies that have rows in the `jobs` table** (verified: the dropdown's 69 entries exactly equal the distinct `company` values in `jobs`).
- A company is "onboarded" if it has a row in `companies` + `company_boards` (all 8 below are onboarded), but it only appears in the dropdown once at least one job survives ingestion.
- Fetch + filter chain: `resumaker.providers.sources.get_source(board.source).list_postings(board.token, **board.extra)` → each stub is filtered by `is_tech_role(title)` AND `is_us_location(location)` (and optionally `matches_preferences`) in `src/resumaker/ingestion/service.py` (`ingest_company`, ~line 38) → `db.upsert_job`.
- **The `is_us_location` / `is_tech_role` filters were verified correct** (they match "United States of America", "Austin, TX, United States", "Software Engineer", etc.). The filters are NOT the cause for any of the 8.

## The 8 companies — verdicts

| # | Company | Live ATS has jobs? | Root cause | Fix category | Effort |
|---|---------|--------------------|------------|--------------|--------|
| 1 | Stripe | ✅ 550 (116 US+tech) | greenhouse ETag `304` cache false-zero | Pipeline bug | Low |
| 2 | Dell | ✅ 342 | Wrong provider in config (Workday → should be Oracle Cloud) | Board config | Low |
| 3 | Walmart | ✅ 917 SWE | Workday adapter under-fetches; `searchText=""` buries tech roles | Adapter logic | Med |
| 4 | Fidelity | ✅ 133 SWE | Same Workday under-fetch pattern | Adapter logic | Med |
| 5 | TD Bank | ✅ 105 SWE | Same Workday under-fetch + Canada-heavy ordering | Adapter logic | Med |
| 6 | Microsoft | ✅ (thousands) | TLS cert mismatch on this network/edge | Environmental | External |
| 7 | Tesla | ✅ | HTTP 403 anti-bot block | Environmental | External |
| 8 | BCG | ✅ ~82 US | Correct Eightfold tenant, but public API won't surface US jobs | Adapter logic (tenant-specific) | High |

---

## 1. Stripe — ETag `304` cache false-zero (PIPELINE BUG)

**Current config:** `source=greenhouse`, `token=stripe`, `extra={}`  ✅ correct.

**Evidence:**
- Direct API `GET https://boards-api.greenhouse.io/v1/boards/stripe/jobs` → **550 jobs**.
- Running the project's filters over those 550: **RAW=550, tech=189, US=294, US+tech (would be stored)=116** (Software Engineer, ML Engineer, AI Engineer in SF/NYC/Seattle, etc.).
- Our adapter returned **0**.

**Root cause:** `src/resumaker/providers/sources/greenhouse.py` stores the response `ETag` in a cache and sends `If-None-Match` on subsequent calls; on **HTTP 304** it returns `[]`. An ETag was cached (almost certainly during onboarding/board-probe) **before** the first real ingest ran, so every ingest since gets `304` → stores nothing → the company stays at 0 permanently. The cache "unchanged" optimization assumes jobs were already persisted, but here they never were.

**Fix direction (for fix agent):**
- The ETag short-circuit must not suppress a fetch when the company currently has **0 persisted jobs**. Options: (a) skip/ignore the `If-None-Match` when the DB has no jobs for that board, (b) treat `304` as "re-fetch fully" on the first successful ingest, or (c) clear the greenhouse ETag cache entry so the next run does a full `200` fetch.
- After fix, expect ~116 US+tech Stripe jobs stored.
- **Note:** this ETag ordering bug may silently affect other greenhouse boards too — worth auditing all `source=greenhouse` companies for the same "ETag cached before first ingest" trap.

---

## 2. Dell — wrong provider (WORKDAY → ORACLE CLOUD) (BOARD CONFIG)

**Current (broken) config:** `source=workday`, `token=dell`, `extra={host: dell.wd1.myworkdayjobs.com, site: External}`.
- Direct Workday POST to that tenant → `total: 0`. The Workday tenant/site does not exist. Dell is not on Workday.

**Correct platform:** The real careers site `https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs` is **Oracle Recruiting Cloud** (same family we already support for JPMC, Amex, Ford, Akamai, Citizens, Staples, Oracle).

**Verified working config:**
```
source = oracle_cloud
token  = dell
extra  = {"host": "enterpriseplatform.dell.com", "site": "CX_1001"}
```
- `siteNumber=CX_1001` was read directly from the careers page HTML.
- Direct Oracle REST `GET https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?...finder=findReqs;siteNumber=CX_1001,...` → **`TotalJobsCount: 342`** with real requisitions returned.

**Fix direction:** Update Dell's `company_boards` row to the config above. The existing `src/resumaker/providers/sources/oracle_cloud.py` adapter handles it unchanged. Expect ~342 raw → US+tech subset stored. No code change required, only the board record.

---

## 3–5. Walmart / Fidelity / TD Bank — Workday adapter under-fetch (ADAPTER LOGIC)

**Configs are correct** (verified reachable). The Workday boards return thousands of jobs, but our adapter surfaces none that pass US+tech.

**Adapter:** `src/resumaker/providers/sources/workday.py` — POSTs with `searchText=""`, `limit=20`, paginating up to ~15 pages (300 max). In practice a run returned only ~40 stubs (2 pages) before stopping/backing off, and Workday's default ordering surfaces retail/branch/pharmacy roles first, so the tech∩US intersection in that shallow window is 0.

**Evidence (direct Workday POSTs):**

| Company | Config (host / site / token) | `total` (searchText="") | `total` for "software engineer" | Our adapter got |
|---------|------------------------------|-------------------------|----------------------------------|-----------------|
| Walmart | walmart.wd504.myworkdayjobs.com / WalmartExternal / walmart | 2000+ | **917** | 40 raw, 0 US+tech |
| Fidelity | fmr.wd1.myworkdayjobs.com / FidelityCareers / fmr | 552 | **133** | 40 raw, 0 US+tech |
| TD Bank | td.wd3.myworkdayjobs.com / TD_Bank_Careers / td | 1601 | **105** | 40 raw, 0 US+tech (tech roles were in Toronto → dropped by us_only) |

Sample of what the shallow fetch returned instead: Walmart "(USA) Tire & Battery Technician", Fidelity "Branch Leader - Dunwoody, GA", TD "Senior Java Developer (Toronto)".

**Root cause:** two compounding issues —
1. **Under-pagination / early stop:** only ~40 of thousands fetched (pagination halts or gets rate-limited/403 after ~2 pages).
2. **No tech-targeted query:** `searchText=""` means relevant SWE/ML roles are buried past the fetched window; they never reach the filters.

**Fix direction (for fix agent):**
- Make Workday pagination robust (respect `total`, keep paging with backoff instead of stopping early; raise the page cap so it can reach thousands of postings, or page until exhausted).
- Consider issuing tech-targeted `searchText` queries (e.g. "software engineer", "machine learning", "data") and/or applying Workday facets, then dedupe — this is how 917/133/105 relevant roles become reachable without pulling the entire catalog.
- These 3 share one adapter, so one fix covers all three (and likely improves other Workday companies).

---

## 6. Microsoft — TLS/network interception (ENVIRONMENTAL, not the ATS)

**Current config:** `source=microsoft`, `token=microsoft` (token ignored), `extra={}`.

**Evidence:**
- Our adapter: `httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] ... certificate is not valid for 'gcsservices.careers.microsoft.com'`.
- Direct `curl` → `HTTP 000`; verbose shows the server presented cert `subject: CN=*.azureedge.net` — "no alternative certificate subject name matches target host name 'gcsservices.careers.microsoft.com'".

**Root cause:** Environmental — Azure Front Door / edge routing (or a network middlebox on this connection) serves a cert that doesn't match the hostname from this IP/network. This is **not** the ATS being empty; Microsoft careers has thousands of roles.

**Fix direction:** Not a code fix in the normal sense. Requires ingesting from a network/IP where the endpoint resolves correctly (e.g., a residential/egress that Azure Front Door routes properly), or a proxy/egress change. The adapter should also surface this failure loudly (it currently raises, but in `ingest_all` the failure per-company should be logged/alerted rather than silently yielding 0). Re-verify from the target deployment environment before assuming code is at fault.

---

## 7. Tesla — HTTP 403 anti-bot block (ENVIRONMENTAL)

**Current config:** `source=tesla`, `token=tesla` (token ignored), `extra={}`.

**Evidence:**
- Our adapter (`curl_cffi` `impersonate="chrome"`) → logs "tesla state non-200", returns `[]`.
- Direct `curl https://www.tesla.com/cua-api/apps/careers/state` → **HTTP 403** (Akamai/`_abck` bot protection).

**Root cause:** Environmental — Tesla blocks this IP/environment at the edge. Jobs exist; the endpoint refuses non-browser/blocked-IP traffic.

**Fix direction:** Needs better anti-bot handling for Tesla: a warmed cookie/session (`_abck`), rotating/residential egress, or a headless-browser fetch path. Not solvable by config. Like Microsoft, the silent `[]`-on-403 should be turned into a visible ingest error so it doesn't masquerade as "0 jobs". Re-verify from the deployment network.

---

## 8. BCG — correct Eightfold tenant, public API won't surface US jobs (ADAPTER LOGIC, tenant-specific)

**Current config:** `source=eightfold`, `token=bcg`, `extra={host: bcg.eightfold.ai, domain: bcg.com}` — this is the **correct** tenant (verified), NOT a typo.

**Evidence:**
- `GET https://bcg.eightfold.ai/api/apply/v2/jobs?domain=bcg.com` with **no location filter** → `count: 163`; paginating pulled all 163. Of those, only **4** are US (even reading the full `locations[]` array), 38 are tech, 1 is US+tech.
- Every location-filtered variant returns **`count: 1`**: `location=United States`, `location=United States of America`, and geo `latitude/longitude/radius` (US-center, radius 2000–3000).
- The real site `https://careers.bcg.com/global/en/search-results` (chip: "United States of America") shows **82 results**, incl. tech like "Principal Database Platform Engineer — Boston, MA".
- Our existing Eightfold company **Netflix works fine** through the same adapter — so the adapter is not broken generally; BCG's tenant behaves differently.

**Root cause:** BCG's Eightfold instance does not expose its US jobs through the generic unauthenticated `GET /api/apply/v2/jobs` location parameters. `careers.bcg.com` fetches its 82 US jobs via a different query the public GET doesn't reproduce (likely a session/POST query with a location facet ID / different endpoint).

**Fix direction (for fix agent):**
- Capture the **live network request** `careers.bcg.com/global/en/search-results` issues when the "United States of America" filter is applied (browser devtools / Playwright). Identify the exact endpoint, method, and location facet/param it uses.
- Either add a BCG-tenant-specific query path to `eightfold.py` (or a small dedicated adapter) using that request, or switch BCG to whatever backend `careers.bcg.com` actually calls.
- Do NOT simply change host/domain — those are already correct; the issue is the query/location mechanism. Expect ~82 US jobs (several tech) once the right query is used.

---

## Suggested fix order (by ROI)

1. **Dell** — one board-record change → +342 jobs. (config only)
2. **Stripe** — fix greenhouse ETag-before-first-ingest bug → +116 jobs. (small code change; audit other greenhouse boards)
3. **Walmart / Fidelity / TD Bank** — Workday adapter: robust pagination + tech-targeted queries → +100s of jobs across 3 companies (one adapter fix).
4. **BCG** — capture live request, add tenant-specific Eightfold query → ~82 jobs. (investigation + code)
5. **Microsoft / Tesla** — environmental; re-verify from deployment network, add anti-bot/egress handling, and make silent failures visible. Not fixable from this network.

## Cross-cutting recommendation

Several adapters (Microsoft raises, Tesla/Workday silently return `[]`/short) let fetch failures masquerade as "0 jobs." Add per-company ingest error surfacing (log/metric/alert) so a blocked or misconfigured board is visibly distinct from a genuinely empty one.
