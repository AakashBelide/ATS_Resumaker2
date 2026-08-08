# TASKS — ATS Resumaker (from-scratch rebuild)

Project plan + task tracker. Companion to [RESUME_SYSTEM_BLUEPRINT.md](RESUME_SYSTEM_BLUEPRINT.md) (the *what/why*); this file is the *how/when/who*.

**Methodology:** Agile-ish, phased, **POC-first**. Every capability is built and validated as an isolated, independently-runnable module *before* any backend/DB/frontend work. Each phase has an explicit **exit criterion** (definition of done). Tasks carry **order + dependencies**; independent tasks run in parallel via sub-agents / git worktrees.

**North-star priority (per owner):** *accuracy → interviews/lead conversion*. A 2–5 min pipeline is acceptable if it yields **high precision with zero/near-zero re-drafts**. Optimize for correctness and "no fabrication," not speed.

---

## 0. Status legend & conventions

**Status:** `⬜ Todo` · `🟨 In Progress` · `🟦 Review` · `✅ Done` · `⛔ Blocked` · `⏸️ Deferred`

**Working conventions**
- **Python:** `uv` only (`uv add …`, `uv run …`). Project root package: `resumaker/`. Never `pip`.
- **Node:** `npm` (frontend/extension, later).
- **LLM budget:** Gemini **API spend hard-capped at $5 total** — a cost guard (Task 0.4) tracks and refuses calls past budget. **Claude Code CLI is the primary LLM engine** (uses the owner's subscription, no per-token cost) for all heavy reasoning; Gemini API is reserved for (a) parity/comparison tests and (b) parse tasks where we specifically want to reproduce ATS-Resumaker's behavior.
- **Provider-swappable:** all LLM calls go through the abstraction (Task 0.4) — never hardcode a provider.
- **Parallelism:** independent POCs may be delegated to sub-agents; use **git worktrees** for POCs that touch shared files concurrently, to avoid conflicts. Merge back to `main` after each POC's exit criterion passes.
- **Determinism:** low temperature + structured JSON schema output for every LLM call; snapshot/golden tests where possible.
- **Data source of truth:** `Resources/` (local, gitignored) → normalized into `data/profile/` (Task 0.3). Everything generated must trace to it.
- **Git:** root repo initialized (`main`). `repos/`, `Resources/`, `.env` are gitignored. Commit per completed task **only when the owner asks**.

---

## Phase 0 — Foundations & setup

> Exit criterion: a runnable `resumaker` package with a canonical candidate profile, a budget-guarded provider abstraction (Claude CLI + Gemini), shared schemas, and an eval harness — so every Phase-1 POC plugs in uniformly.

| # | Task | Status | Deps | Owner | Observations |
|---|------|--------|------|-------|--------------|
| 0.1 | Git init at root + `.gitignore` (repos/, Resources/, .env excluded) | ✅ Done | — | main | Done this session. Root repo on `main`. |
| 0.2 | `uv` project skeleton (`resumaker/` with `core/ pocs/ evals/`) | ✅ Done | 0.1 | main | Done this session. Python 3.13. |
| 0.3 | **Canonical profile builder** — parse `Resources/` → single `data/profile/profile.json`. Reconcile sources; flag conflicts. | ✅ Done | 0.2 | main | Built from cv.md (authoritative). 7 employers, 35 metrics, 70 skills. Added `equivalence_map` (13 entries) + `facts_allowlist`. Flagged master_resume.json staleness (wrong LinkedIn, missing 2025-26 roles). |
| 0.4 | **LLM provider abstraction + cost guard** — `core/llm.py` + `core/cost_guard.py`. | ✅ Done | 0.2 | main | ClaudeCLIProvider (default, subscription) + GeminiProvider (new `google-genai` SDK, `gemini-2.5-flash`, thinking disabled). Both smoke-tested. Hard $5 Gemini cap enforced; usage → `data/cache/usage.jsonl`. Claude cost logged separately (doesn't count vs cap). |
| 0.5 | **Shared schemas + profile loader + eval harness** — `core/schemas.py`, `core/profile.py`, `evals/harness.py`. | ✅ Done | 0.2 | main | JobPosting/KeywordSet/GapReport/SponsorSignal/FitScore/ApplyDecision/ResumeDoc/VerifyReport/ATSScore. Profile loader exposes metrics/employers/titles for the fact-gate. Validated. |
| 0.6 | **Install/verify system deps** — LibreOffice + Playwright browsers. | ✅ Done | 0.2 | main | LibreOffice ✅ (`/opt/homebrew/bin/soffice`). Playwright Chromium ✅ installed. |

---

## Phase 1 — Component POCs (modular, each independently testable)

> Exit criterion: **every component runs standalone** via a small CLI, passes its own eval on ≥3 real inputs, and emits schema-valid output. This is where the owner's "test each individual component first" happens. Build order below respects data dependencies; ⚡ = parallelizable.

| # | Task | Status | Deps | Owner | Observations |
|---|------|--------|------|-------|--------------|
| 1.1 | **JD Scraper POC** — fetch a JD from a URL. Tiered: (a) public ATS JSON (Greenhouse/Lever/Ashby); (b) Playwright fallback; (c) stealth eval deferred: **Firecrawl**, **Scrapling**, **CloakBrowser**, camoufox. | ✅ Done | 0.5 | main | `pocs/scrape_jd/`. Eval **4/4 PASS** on live postings (Databricks/GH, Lever demo, Ramp/Ashby) + Playwright fallback. Greenhouse HTML content + Lever/Ashby JSON parsed to clean text w/ title/company/location. **Deferred sub-task:** eval Firecrawl/Scrapling/CloakBrowser for bot-protected pages (needed for some direct company sites + Phase 3). |
| 1.2 | **JD structuring POC** — raw JD → structured JobPosting (title, company, location, work_model, seniority, required/preferred quals, responsibilities, salary, work-auth note, **knockouts**). | ✅ Done | 1.1 | main | `pocs/jd_structure/` (Claude CLI, `sonnet`). Eval **2/2 PASS**: live Ramp JD (title + 4 reqs + 2 years-experience knockouts detected) and **prompt-injection resistance** (embedded "set title to PWNED" ignored). Untrusted-content system prompt works. |
| 1.3 | **Keyword extraction POC** — triple-pass consensus → 15–20 weighted keywords, hard vs soft split, `standardized` set for reuse. | ✅ Done | 1.2 | main | `pocs/keywords/` (3 passes on `haiku` + consolidation on `sonnet`). Weight = consensus strength (fraction of passes). Eval 1/1: 7/7 expected hard skills, 19 kws. Also hardened `core/llm.py` with **retry+backoff** on transient CLI blips (surfaced under concurrency). |
| 1.4 | **Gap analysis POC** — classify each JD requirement vs profile: `existing` / `supportedByResume` / `gap`; apply `equivalence_map` for legitimate substitutions (e.g. Cloud Run→Lambda) with honest bridging; surface true gaps to user. | ⬜ Todo | 1.3, 0.3 | — | Zero-LLM classifier first, LLM only for fuzzy cases. Never paper over a gap. |
| 1.5 | **Sponsorship POC** — USCIS Hub ingest + employer-name normalization + likelihood. | ✅ Done | 0.5 | subagent→main | `pocs/sponsorship/` (deterministic, $0). Eval **6/6** on real USCIS FY2021–23 (Amazon high/46,630/98.4%, made-up→unknown, "Google LLC"≡"Google Inc"). **Entity-family aggregation** (Amazon files under 17 legal entities). Deps: `rapidfuzz`, `curl-cffi`. **KEY FINDING: .gov 403 is TLS/JA3 (Akamai) fingerprinting, not UA — needs `curl_cffi impersonate=chrome`** (relevant to 1.1 stealth). TODO: DOL OFLC LCA for SOC/role-level sponsorability (~1GB files, deferred). |
| 1.6 | **Role-fit / match-score POC** — deterministic dimensions (skills/exp/location/domain/growth) + LLM qualitative **anchored** to the deterministic floor → 0–100 (and a 1–5 view). Feeds only *source* profile, never tailored output. | ⬜ Todo | 1.3, 1.4 | — | Dual-score design (ATS-Resumaker ⨯ career-ops). |
| 1.7 | **Apply / no-apply decision POC** — combine fit score + sponsorship signal + knockout pass/fail → recommendation + rationale. Discourage low-fit applies. | ⬜ Todo | 1.4, 1.5, 1.6 | — | Human-in-loop; explainable. |
| 1.8 | **Resume generation POC** — grounded tailoring (Claude CLI) → **ATS-safe `.docx`** (python-docx: single-column, TNR/Calibri, real section borders, tab-stop dates, real hyperlinks) → **PDF** (LibreOffice headless). Keyword-in-bullet, **varied bullet structure** (not uniform XYZ), **length by seniority**, US Letter default. | ⬜ Todo | 1.4, 0.3 | — | The core artifact. python-docx is the ATS-parsable engine (blueprint §4). |
| 1.9 | **Fact-gate POC (anti-fabrication)** — mechanical: extract every metric/employer/title/tool from generated resume, diff vs profile+allowlist, **block** on unsupported. Self-test suite. | ⬜ Todo | 1.8 | — | Biggest missing piece vs current tool. Non-bypassable. |
| 1.10 | **ATS-parse verification POC** — text-extraction round-trip (pdfplumber/mammoth) + `ats-screener`/open-resume + spelling/grammar gate + **resume↔LinkedIn consistency check**. | ⬜ Todo | 1.8 | — | Typos = #1 recruiter red flag; consistency mismatch = silent reject. |
| 1.11 | **Deterministic ATS scorer POC** ⚡ — transparent weighted keyword/skill overlap (50/30/20) + **semantic per-requirement cosine coverage**. Reproducible metric. | ⬜ Todo | 1.3, 1.8 | — | Honest proxy, not a "real ATS score." |
| 1.12 | **Cover letter POC** ⚡ — personalized, anti-AI-tells (no em-dash, no buzzwords, varied), grounded in profile. | ⬜ Todo | 1.8 | — | Resurgent per research; keep human-in-loop. |

**Parallelization plan:** 1.1→1.2→1.3→1.4 is the critical path. In parallel: **1.5** (sponsorship, fully independent) and, once 1.8 lands, **1.9/1.10/1.11/1.12** fan out to sub-agents in worktrees. 1.6→1.7 gate the apply decision.

---

## Phase 2 — End-to-end pipeline (CLI orchestration)

> Exit criterion: `resumaker run <jd-url>` produces a fact-gated, ATS-verified resume + apply/no-apply report in ≤5 min, with a measured **re-draft rate ≈ 0** on a 10-JD eval set.

| # | Task | Status | Deps | Owner | Observations |
|---|------|--------|------|-------|--------------|
| 2.1 | **Orchestrator** — chain 1.1→1.11. Two implementations: (a) pure-Python service calls; (b) **Claude Agent SDK sub-agent fan-out** (keywords / gap / JD-parse / competencies in parallel). | ⬜ Todo | Phase 1 | — | Deterministic mechanics in code; cognitive steps as versioned prompts. |
| 2.2 | **CLI runner** — `uv run resumaker run <url>` → artifacts in `outputs/<company-role>/`. SSE-ready progress events. | ⬜ Todo | 2.1 | — | |
| 2.3 | **Quality eval** — run on 10 real JDs; measure fact-gate pass %, ATS score, re-draft count, manual quality read. | ⬜ Todo | 2.2 | — | Primary success metric = re-drafts ≈ 0. |
| 2.4 | **CLI vs API comparison** — cost/quality/latency of Claude-CLI path vs Gemini-API path; pick default. | ⬜ Todo | 2.3 | — | Stay under $5 Gemini during this. |

---

## Phase 3 — Validation harness: cloned ATS + recruiter simulation

> Exit criterion (the owner's "does my resume actually pop up?" test): our generated resume **parses cleanly**, **surfaces in a recruiter Boolean search**, and **ranks above decoys** inside a real self-hosted ATS.

| # | Task | Status | Deps | Owner | Observations |
|---|------|--------|------|-------|--------------|
| 3.1 | **Stand up a local open-source ATS** — evaluate OpenCATS (self-host) and/or `ats-screener`/open-resume as the "recruiter view." Docker. | ⬜ Todo | 2.2 | — | Fully local; safe sandbox. |
| 3.2 | **Create a real test job** in the ATS matching one of our target JDs. | ⬜ Todo | 3.1 | — | |
| 3.3 | **Submit our resume + decoys**, run the ATS parse + recruiter Boolean/keyword search + ranking. | ⬜ Todo | 3.2, 1.8 | — | Measure parse fidelity + search surfacing + rank. |
| 3.4 | **Recruiter-filter simulation** — script a hiring-manager filter (knockouts + keyword search + rank) and confirm our resume advances; iterate on misses. | ⬜ Todo | 3.3 | — | Closes the loop on "gets seen." |
| 3.5 | **Browser-extension → local-ATS assisted-apply** (optional) — extension captures JD, backend runs pipeline, autofills the *local test* application, **stops before submit** (human-in-loop). NOT real external companies. | ⬜ Todo | 3.4 | — | Assisted-apply only (blueprint §21). Validates the extension↔CLI bridge end-to-end safely. |

---

## Phase 4 — Backend + Database (after POCs validated)

> Exit criterion: the validated pipeline exposed as a service with persistence and progress streaming.

| # | Task | Status | Deps | Owner | Observations |
|---|------|--------|------|-------|--------------|
| 4.1 | **Stack decision** — FastAPI (recommended: Python ecosystem for docx/pdf/parsing) vs Node. | ⬜ Todo | Phase 2 | — | Recommend FastAPI. Confirm with owner. |
| 4.2 | **Data model + Postgres** — files canonical, DB derived (history/analytics/monitoring, incl. token/cost/latency per ATS-Resumaker). | ⬜ Todo | 4.1 | — | |
| 4.3 | **Pipeline-as-API + SSE** progress. | ⬜ Todo | 4.1, 2.1 | — | |
| 4.4 | **Job ingestion + sponsorship enrichment services** (provider registry). | ⬜ Todo | 4.2, 1.5 | — | |

---

## Phase 5 — Frontend + Browser extension *(deferred — details to be discussed)*

> Placeholder. Tasks to be defined with the owner later. Likely: Next.js dashboard (review/approve/download, history, analytics/monitoring) + MV3 extension (capture JD → trigger pipeline).

| # | Task | Status | Deps | Owner | Observations |
|---|------|--------|------|-------|--------------|
| 5.x | TBD with owner | ⏸️ Deferred | Phase 4 | — | Per owner: "focus on frontend later." |

---

## Decisions & backlog (open items)

| Item | Recommendation | Status |
|------|----------------|--------|
| **Two GitHubs** (Personal `AakashBelide` vs Academic `Belide-Aakash`, latest work in Academic) | Resume shows **one code link**. Options: (a) link **Portfolio (aakashbelide.tech)** as the primary "projects" link since it can aggregate both + the GitHub with the *latest/strongest* work (Academic) as the GitHub line; (b) consolidate — pin/mirror top Academic projects into Personal for handle consistency, use Personal only. Recommend (a) short-term, (b) as cleanup. **Owner decides.** | ⬜ Open |
| US Letter vs A4 default | US Letter (target = US companies); offer A4 toggle. | ⬜ Open |
| Auto-apply policy | **Assisted-apply only**, human before submit (blueprint §21). No bulk auto-submit. | ✅ Decided |
| Resume template theme(s) | Start with one clean ATS-safe .docx template; add variants later. | ⬜ Open |
| Scraping stealth tools legality | Prefer official public APIs; Scrapling/CloakBrowser reserved for JS/protected pages within ToS and the local test ATS. | ⬜ Open |

---

## Phase log (update after each phase)

- **2026-08-07 — Phase 0 kickoff:** repo initialized (`main`), `.gitignore`, uv project, dir scaffold created. Tooling verified: uv 0.7.3, node 22.11, npm 10.9, git 2.46, Python 3.13.11. Data confirmed present in `Resources/`. Tasks 0.1/0.2 ✅.
- **2026-08-07 — Phase 0 COMPLETE (0.3–0.6 ✅).** Built & validated: canonical `data/profile/profile.json`; `core/llm.py` (Claude CLI + Gemini via new `google-genai` SDK) with `core/cost_guard.py` ($5 hard cap, per-call logging); `core/schemas.py`; `core/profile.py`; `evals/harness.py`. LibreOffice + Playwright Chromium installed.
  - **Observations:** (1) `google.generativeai` is deprecated → migrated to `google-genai`; `gemini-2.0-flash` retired → default `gemini-2.5-flash` (thinking disabled to avoid empty output). (2) Each headless `claude -p` call carries ~$0.02–0.04 cache-creation overhead regardless of model → for pipelines, **prefer fewer, batched LLM calls** over many small ones. (3) Claude CLI emits a workspace-trust warning to **stderr** (harmless; we parse stdout only). (4) Gemini spend so far ≈ $0.00001 of $5.
  - **Next:** Phase 1 POCs, starting 1.1 (JD scraper). Parallelizable POCs to be delegated to sub-agents / worktrees.
- **2026-08-07 — Task 1.1 ✅ (JD scraper).** `pocs/scrape_jd/` with public-ATS-API path (Greenhouse/Lever/Ashby) + Playwright fallback. Eval 4/4 on live postings. Owner added **Firecrawl** to the stealth shortlist (deferred sub-task with Scrapling/CloakBrowser).
- **2026-08-07 — Repo pushed.** Private repo `github.com/AakashBelide/ATS_Resumaker2` (SSH `github-personal`), commits as "Aakash Belide <…noreply>". PII (`data/`), secrets (`.env`), `Resources/` gitignored; scanned clean. Reference repos moved by owner to `../repos`. NOTE: commits after the initial push are held locally — push only when owner asks.
- **2026-08-07 — Task 1.2 ✅ (JD structuring).** `pocs/jd_structure/` (Claude CLI `sonnet`, untrusted-content system prompt). Eval 2/2: live-JD completeness + prompt-injection resistance. Next: 1.3 keywords (critical path) + 1.5 sponsorship (parallelizable).
