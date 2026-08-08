# ATS Resume System — Build Blueprint & Do's/Don'ts

> A from-scratch design playbook synthesizing learnings (good **and** bad) from three real projects — **Job-Ops** (dakheera47), **career-ops** (santifer), and **ATS-Resumaker** (yours) — cross-checked against 2025–2026 research on how US ATS, recruiters, and job/visa data sources actually work.
>
> **The single most important reframing:** Resumes are almost never auto-rejected by a keyword-score bot (that's a debunked 2012 myth — 92% of recruiters don't configure content auto-rejection). There are **two real gates**: (1) the **machine gate** — parse cleanly into fields + be *findable* in recruiter search + pass **knockout questions** (work auth, location, years, degree) which are the real auto-filter; and (2) the **human gate** — the recruiter's ~6–7 second first-pass scan and the credibility check that follows. The human gate is where nearly all real rejections happen. Design for both, but never sacrifice the human gate to win a machine gate that mostly doesn't exist.

---

## Table of Contents
1. [Tailoring for the ATS (parsing, keywords, metrics)](#1-tailoring-for-the-ats)
2. [Tailoring for the recruiter (spacing, natural voice)](#2-tailoring-for-the-recruiter)
3. [Grounding to real experience (guardrails, anti-fabrication)](#3-grounding-anti-hallucination)
4. [How & what to generate an ATS-compliant resume with (format + tooling)](#4-generation-format--tooling)
5. [Mechanisms to make the resume solid (gap analysis, source of truth, keywords)](#5-solidity-mechanisms)
6. [Mandatory resume sections](#6-mandatory-sections)
7. [One page vs two pages (by seniority)](#7-length-1-vs-2-pages)
8. [What parts of the JD to concentrate on](#8-jd-focus)
9. [Handling gap skills via equivalent tools](#9-equivalent-tool-substitution)
10. [Parsing & verifying the final resume (old + new ATS)](#10-final-verification)
11. [Adapting to AI/semantic ATS](#11-semantic-ats)
12. [Deterministic ATS scoring](#12-deterministic-scoring)
13. [Scoring the JD/role fit against you (0–5 vs 0–100)](#13-role-fit-scoring)
14. [Checking H-1B / sponsorship](#14-sponsorship-data)
15. [Job boards & APIs for pulling jobs](#15-job-board-apis)
16. [Using agent CLIs (Claude Code/Codex) + extension integration](#16-agent-cli-architecture)
17. [Consistency, determinism & verification tests](#17-consistency--determinism)
18. [Plugging in any LLM / using your own CLI subscription](#18-llm-provider-abstraction)
19. [Best architecture & technologies](#19-architecture)
20. [Packaging, release & mobile](#20-packaging--mobile)
21. [Auto-apply — should you?](#21-auto-apply)

---

## 1. Tailoring for the ATS
*(parsing, keywords, metrics)*

**Context / learnings:** Job-Ops rewrites only headline/summary/skills; career-ops reformulates 15–20 JD keywords across summary + first bullets + skills; ATS-Resumaker injects keywords into every bullet ("keyword proof") + rule-based bolding. Research: keyword matching drives *recruiter search & ranking*, not auto-rejection. "Keyword proof" (skills demonstrated in achievement bullets) beats a keyword list.

**✅ Do**
- Put keywords **where they're proven** — inside quantified achievement bullets, not just a Skills list. This is ATS-Resumaker's biggest edge and matches how recruiters search and how semantic ATS score.
- Distribute target keywords: top of summary (5 most critical), first bullet of each relevant role, and the Skills section — career-ops's pattern.
- Match the **exact JD job title** in your headline/most-recent title framing when truthful — title is the #1 thing recruiters search and scan (Job-Ops treats this as "the #1 ATS factor").
- Use the JD's **exact vocabulary/acronyms** ("React" vs "ReactJS", "TDD" vs "Unit Testing") — reformulate your real experience into their words.
- Use standard section headings (Experience, Skills, Education) and **"Month YYYY"** date format — numeric-only/year-only dates cause false gaps in 3–4 systems.

**❌ Don't**
- Don't keyword-stuff or hide white-text keywords — semantic ATS penalize repetition, and recruiters reject visible stuffing.
- Don't leave the experience body generic (Job-Ops's weakness — it never rewrites bullets, so the body under-indexes for search).
- Don't invent a keyword you can't back with real experience (see §3, §9).
- Don't rely on a keyword *count* — context and quantified evidence beat raw count for both semantic matchers and humans.

---

## 2. Tailoring for the recruiter
*(spacing, natural voice, human readability)*

**Context / learnings:** career-ops has the strongest anti-AI-slop voice layer + an `--hm-audit` that literally simulates the specific reviewer. ATS-Resumaker's every-bullet Google-XYZ format risks reading robotic. Research: the scan is **two passes** — an initial **F-pattern triage of ~7 seconds** (name → current title → past titles → last-two-role dates → education, ~80% of first-glance time on those six points), and *only if you survive it*, a **30–60 second real read**. Backlash is hardening: **62% of employers more likely to reject un-personalized AI resumes**, **~49% auto-dismiss suspected-AI resumes**, ~20% reject outright, and **~33% claim to spot AI in under 20 seconds**. Note the platform split: **Workday runs a title-matching ranking engine** (exact title/seniority alignment matters a lot), while **Greenhouse is human-facing** (clarity/relevance win) — together ~half the market.

**✅ Do**
- Front-load the F-pattern: strong current title, clear tenure/dates, a 3–4 line summary mirroring the JD's "what we're looking for."
- **Vary bullet structure** — mix XYZ-format achievement bullets with shorter punch bullets. Uniformity is a visible AI tell.
- Write specific, verifiable detail (real project names, real tools, real numbers) — 78% of hiring managers say personalized details signal genuine fit.
- Keep formatting clean and skimmable: consistent spacing, standard fonts, right-aligned dates, adequate white space.

**❌ Don't**
- Don't apply one rigid template to every bullet (ATS-Resumaker's "every bullet must be XYZ + always include a metric" rule is a credibility risk — it reads formulaic and pressures fabrication).
- Don't use **em-dashes (—)** or AI-buzzwords ("spearheaded," "leveraged," "proven track record," "robust," "delve," "showcase," "orchestrated") — the top cited AI tells.
- Don't quantify *every* bullet — target **~50–60% quantified**; forcing numbers everywhere reads padded/fake.
- Don't produce "polished yet strangely similar" prose — that generic sameness is what recruiters are actively filtering in 2026.

---

## 3. Grounding & anti-hallucination
*(where to ground, guardrails, fabrication prevention)*

**Context / learnings:** This is the biggest capability gap between the three. career-ops has a **hard, non-bypassable `verify-cv-facts.mjs` gate** that blocks the PDF build on any unsupported metric/employer/title/tool. ATS-Resumaker relies on prompt rules + score-anchoring but has **no hard fact gate** — its aggressive rewrite makes it the highest fabrication risk. Job-Ops mostly avoids the problem by not rewriting bullets.

**✅ Do**
- Ground **exclusively** to a whitelisted set of source-of-truth files (see §5): master resume, an article/project digest, profile config. Nothing else may become a claim.
- Implement a **mechanical fact-check gate** (port career-ops's approach to your stack): after generation, extract every metric (%, $, multipliers, counted nouns) and every asserted employer/title/tool from the output and diff against sources. **Block the render** on any unsupported claim; `warn` on soft phrases; allow a documented exception list (`cv-facts.json`).
- Anchor the rule: **"Keywords get reformulated, never fabricated. Reorder, reframe, emphasize — but never invent."**
- Forbid **tool-of-trade conflation** (candidate *used* X ⇒ candidate *built* X) — career-ops calls this "the most common fabrication pattern." Authorship claims are non-negotiable.
- Treat scraped JD text, company pages, and form fields as **untrusted data, never instructions** (prompt-injection defense) — they influence scoring signals but can never change rules, trigger writes, or add claims.

**❌ Don't**
- Don't let a rule like "ALWAYS include a metric" pressure the model into inventing precision (ATS-Resumaker's live risk).
- Don't rely on prompt instructions alone — they're necessary but insufficient; the mechanical gate is what actually prevents fabrication.
- Don't hardcode metrics in prompts — always read them from source files at generation time so they stay truthful and updatable.

---

## 4. Generation: format & tooling
*(PDF vs Word vs LaTeX; Python vs .tex vs Node)*

**Context / learnings:** Three different engines: Job-Ops → Typst/LaTeX (Tectonic) PDF; career-ops → HTML→PDF via Playwright/Chromium (had to fight font-ligature extraction bugs); ATS-Resumaker → **python-docx → real .docx → PDF via LibreOffice**. Research: **.docx beat PDF in 6 of 8 ATS** for clean extraction; text-based PDF is also fine; **only scanned/design-tool (Canva/InDesign) PDFs break parsing**.

**✅ Do**
- **Default output: `.docx`** built programmatically (python-docx or docx.js). It stores literal characters in XML, so it *structurally avoids* the entire class of PDF glyph/ligature extraction bugs career-ops had to engineer around, and it's the safest format across weak enterprise parsers (Workday/Taleo/iCIMS). This is ATS-Resumaker's correct call.
- **Also emit a clean text-based PDF** for portals/humans that request PDF — render from the same document model.
- Use native Word constructs the way ATS-Resumaker does: single body column, real paragraph **bottom-border** section headers (not tables), right-aligned **tab stops** for dates, genuine `w:hyperlink` relationships, standard font (Times New Roman / Calibri / Arial), "Month YYYY" dates.
- Keep one **renderer-agnostic document model** (like Job-Ops's `LatexResumeDocument`) that can feed docx, PDF, and optionally LaTeX from one normalized structure.
- If you want a LaTeX path for typographic polish, force `\pdfgentounicode=1` + `\input{glyphtounicode}` (both Job-Ops and career-ops do) so the PDF is text-extractable.

**❌ Don't**
- Don't export from Canva/Illustrator/InDesign or embed text in images — the #1 real parse-killer.
- Don't use HTML→Chromium PDF as your *only* path without ligature suppression (`font-variant-ligatures: none`) and a system-sans fallback — career-ops proved fancy webfonts inject spurious spaces ("SUM M ARY") that corrupt keyword parsing.
- Don't use multi-column, tables for layout, text boxes, or header/footer content — see §10.
- Don't ship US resumes on A4 without offering US Letter — ATS-Resumaker hardcodes A4; US companies expect Letter (parsing is unaffected, but it's a polish/print detail).

**Tooling verdict:** Python backend with **python-docx** for the canonical `.docx`, **LibreOffice headless** (`soffice --headless --convert-to pdf`) for deterministic server-side PDF (docx2pdf/Word only as a local-dev fallback). Node/Playwright HTML path is optional for a visually richer "human" variant, not the ATS variant.

---

## 5. Solidity mechanisms
*(gap analysis, source-of-truth file, keyword usage)*

**Context / learnings:** career-ops is the model here: canonical `cv.md` + `article-digest.md` + `profile.yml` as exclusive sources; a **zero-LLM skill-gap classifier** (`jd-skill-gap.mjs`) run *before* drafting that buckets JD requirements into `existing` / `supportedByResume` / `gap`; "files are canonical, DB is derived."

**✅ Do**
- Maintain a **single canonical source-of-truth** (a rich master resume / experience inventory) that is git-diffable and human-editable. Everything generated must trace to it.
- Run a **pre-draft gap analysis** classifying each JD requirement as:
  - `existing` — already a named skill → safe to lead with
  - `supportedByResume` — demonstrated in prose but not named → legitimate to surface in Skills "in the user's own words"
  - `gap` — no trace → **surface to the user explicitly; never paper over with an invented claim** (see §9 for the equivalent-tool exception)
- Keep a **standardized keyword set** per JD (extract once, reuse) so tailoring *and* scoring are consistent across runs (ATS-Resumaker's `standardized_keywords`).
- Store an **article/project digest** that takes precedence for project metrics, so numbers are always the real ones.

**❌ Don't**
- Don't let the DB be the source of truth — make files/canonical JSON authoritative and the DB a rebuildable derived index.
- Don't silently bridge a `gap` — that's exactly the fabrication path.
- **Fix the latent bug you inherited:** in ATS-Resumaker's one-page loop, `_rewrite_overflowing_bullets` and `_condense_resume` reference an undefined `usage` var → `NameError` swallowed by `except` → the loop silently no-ops. Any solidity mechanism must have tests proving it actually runs (see §17).

---

## 6. Mandatory sections

**Research-backed (US, 2026):**

**✅ Mandatory:** Contact (name, phone, email, city/state, LinkedIn/portfolio URL — in the **body**, not header/footer), **Work Experience**, **Skills**, **Education**.

**Location presentation matters more than people think** (see [Appendix B](#appendix-b-location--the-full-pre-advance-screening-checklist)): ~43% of recruiters apply a location radius filter (often "within 50 miles") *before* a human reads anything, and location doubles as a ranking signal. So: use **City + Major Metro + State** ("Denver, CO", not the suburb "Broomfield, CO"), in the body; add **"(Open to Remote)"** for remote roles; use **"Relocating to Austin, TX (Q3 2026)"** — specific + committed — when moving. **Never** list a full street address (privacy + distance bias), a ZIP alone (radius deprioritization), or "Remote" with no city/state (excludes you from state-scoped searches).

**✅ Strongly recommended:** **Professional Summary** (3–4 lines, tailored to JD) — summaries get ~2.3× more interview requests than objectives.

**✅ Context-dependent:** Projects (essential for new grads/tech), Certifications, Awards, Publications (academic), Volunteer.

**Order:** Contact → Summary → *(experienced: Experience first)* / *(new grad: Education + Projects higher)* → Skills → Education/Certs.

**❌ Don't include (US — bias/legal):** photo/headshot, date of birth/age, marital status, full street address. Objective statements are effectively dead except for career-changers/first resume.

---

## 7. Length: 1 vs 2 pages

**Research-backed norms (US, 2026):** the rigid "always one page" rule is fading — a 2025 survey of 1,013 HR pros found **82% prefer 1–2 pages, 51% prefer two.**

| Seniority | Length |
|---|---|
| New grad / student / <5 yrs | **1 page** (still effectively required) |
| Mid-career (~5–15 yrs) | 1–2 pages; 2 acceptable when depth is relevant |
| Senior / director+ / 15+ yrs | **2 pages is the new standard** |
| Academic CV | multi-page (publications) |
| US federal (USAJOBS) | **capped at 2 pages** as of Sept 27, 2025 |

**By industry:** finance/IB/consulting still lean strict 1-page for juniors; tech tolerates 1–2 + GitHub links.

**✅ Do** make the page target a **function of seniority + JD**, not a hardcoded constant. Keep ATS-Resumaker's physical one-page *loop* but drive its target from role level (1 page for early-career, allow 2 for senior). **❌ Don't** cram a senior candidate onto one page or pad a new grad to two.

---

## 8. JD focus
*(what to concentrate on when drafting)*

**✅ Do concentrate on, in priority order:**
1. **Exact job title** (headline/title match — #1 search + scan factor).
2. **"Required qualifications" / "must-haves"** — these map to knockout questions and recruiter search filters; every truthful one should be represented.
3. **Hard skills / tools / technologies** — weighted far more heavily than soft skills by scoring tools; these are what recruiters Boolean-search.
4. The **"About you" / "What we're looking for"** section — mirror it in the summary (career-ops's "hook").
5. **Responsibilities** — map your real bullets to the top 3–5.
6. **Seniority signals** (years, scope, team size) — align framing, never fabricate.
7. **Knockout criteria** — location/onsite, work-auth/**sponsorship**, minimum years, degree, license/clearance, salary range. These are **hard binary gates on the application form that auto-reject before any human sees the resume** and remove ~40% of applicants. Detect them in the JD, pre-fill truthful answers, and warn the user when one is a hard fail (see [Appendix B](#appendix-b-location--the-full-pre-advance-screening-checklist), §13, §14).

**❌ Don't** over-index on soft skills or company boilerplate/mission fluff, and don't chase every "nice-to-have" at the expense of the must-haves.

---

## 9. Equivalent-tool substitution
*(mentioning alternative tools that match a gap skill)*

> Your example: JD wants **AWS Lambda**; source has **GCP Cloud Run** (same serverless fundamentals). How to represent this honestly.

This is the **legitimate middle path between fabrication and omission** — but it must be truthful and transparent. career-ops's cover-letter rule already sanctions this: *"If the job asks for Linux and the candidate has Docker/Kubernetes, you CAN write that their infrastructure experience translates well. Do not lie, but do bridge the gap logically."*

**✅ Do**
- Represent it in **experience/summary as your real tool**, then **bridge explicitly**: *"Built and deployed serverless functions on **GCP Cloud Run** (directly transferable to **AWS Lambda** — same event-driven, containerized serverless model)."*
- In **Skills**, you may list the equivalent with an honest signal — e.g. a "Transferable / familiar" grouping, or `Serverless (GCP Cloud Run; AWS Lambda-equivalent)`. This makes the resume findable for "AWS Lambda" search **without claiming production AWS experience.**
- Maintain a curated **equivalence map** in your source-of-truth config (Cloud Run↔Lambda↔Azure Functions; BigQuery↔Redshift↔Snowflake; Postgres↔MySQL; PyTorch↔TensorFlow; etc.) so substitutions are deterministic and reviewable, not LLM-improvised.
- Require the substitution to pass the fact gate as a **declared, allow-listed equivalence**, not a raw invented tool.

**❌ Don't**
- Don't write "AWS Lambda" bare in an experience bullet as if you shipped it in production — that's fabrication that collapses in interview.
- Don't let the LLM invent equivalences freely — gate them through the curated map + user confirmation, and flag borderline ones as `gap` (see §5).

---

## 10. Final verification
*(parse-checking against old + new ATS)*

**Context / learnings:** career-ops runs a section-order guard + page-budget guard + ATS unicode normalization at render time. Research: the most reliable local test is **extract the text and check linear order/completeness** — if extraction is jumbled, real ATS will fail too.

**✅ Do — build a verification stage that runs on every generated resume:**
- **Text-extraction round-trip:** extract with `pdfplumber`/`pdfjs` (PDF) and `mammoth`/`python-docx` (DOCX); assert the linear text order matches intended order and no section/contact info is missing or jumbled.
- **Structure guards:** section headings present + in expected order; contact info in body (not header/footer); dates in "Month YYYY"; no tables/text-boxes/multi-column; no images with text.
- **Unicode/ASCII normalization** (career-ops's `normalizeTextForATS`): em/en-dash→`-`, smart quotes→straight, ellipsis→`...`, strip zero-width chars, nbsp→space.
- **Run against an ATS simulator:** `sunnypatell/ats-screener` (open source, simulates Workday/Taleo/iCIMS/Greenhouse/Lever/SuccessFactors), and/or `open-resume`'s readability parser. Use these as CI checks.
- **Spelling/grammar gate:** run a spell/grammar check on the final text and block on errors. This is cheap and high-value — **typos are the #1 recruiter red flag (85% have rejected a candidate over one, 58% cite it as top red flag)**. A single typo undoes all the tailoring.
- **Page-budget guard** tied to the seniority target from §7.

**❌ Don't** ship without the extraction round-trip — it's the single highest-value, cheapest ATS check and catches the failure modes that actually matter for both old (Taleo) and new (Ashby) systems.

---

## 11. Semantic / AI ATS
*(keyword-in-context, not just presence)*

**Context / learnings (well-sourced):** Eightfold, Workday (HiredScore + Skills Cloud + Illuminate), Beamery, SeekOut, LinkedIn Recruiter are moving to **embedding + knowledge-graph + LLM ranking**. They vectorize resume and JD, score **skill overlap (embedding clusters), recency, and career trajectory**, and produce a 0–5 rating with explainable reasoning. A 70%-keyword resume with 3 concrete measurable outcomes can beat a 95%-keyword resume with none.

**✅ Do**
- Write **skill + action + result + context** bullets so the model can infer *proficiency*, not just presence. This is the strongest reason to keep ATS-Resumaker's keyword-in-bullet approach — but grounded and varied.
- Surface **recency** — put current/recent use of target skills prominently; recency is an explicit signal.
- Use standard **skills-taxonomy** language and clear titles; you no longer need to chase every synonym (the model handles synonymy) — so lean effort into *evidence* over *keyword permutations*.
- Add a **semantic self-check** to your pipeline: embed each JD requirement and each resume bullet, compute cosine similarity per requirement, and flag requirements with weak coverage. This mirrors how Eightfold/Workday actually match and gives you a truthful "what's under-evidenced" list.

**❌ Don't** stuff synonyms (backfires on semantic matchers), and don't assume presence = credit — the model weights contextual, quantified, recent evidence.

---

## 12. Deterministic ATS scoring

**Context / learnings:** ATS-Resumaker's `ATSScorer` is a genuinely deterministic 0–100: **keyword match 50% + quantification 30% + structure 20%**, then it **anchors the LLM's subjective score to that deterministic floor** to prevent hallucinated zeros. Research: Jobscan/Teal/Resume Worded are all deterministic keyword/skill-overlap scorers (weights mostly proprietary); a truly deterministic score is only possible for keyword/skill overlap — you *cannot* reproduce a real ATS or semantic score (proprietary ML).

**✅ Do**
- Implement your **own transparent deterministic scorer** (extract JD skill set → weight by frequency/importance → weighted coverage/Jaccard) as your stable, reproducible metric. Weight **hard skills > soft skills** (Jobscan's approach). Aim ~75%+ as the "good" band.
- Keep the **dual-score design** (deterministic + LLM-qualitative anchored to it) — this is ATS-Resumaker's best idea and career-ops independently reached the same conclusion.
- Add the **semantic per-requirement cosine coverage** (from §11) as a second deterministic-ish axis.

**❌ Don't** present the score as "your real ATS match" — be honest it's a keyword/skill-overlap proxy, not a hiring prediction. **❌ Don't** let the LLM return 0 or free-floating numbers — always anchor to the deterministic floor.

---

## 13. Role-fit scoring
*(is this even the right role? — career-ops 0–5 vs Job-Ops 0–100)*

**Context / learnings:** Two philosophies. Job-Ops scores the **job 0–100** against the profile (skills 30 / experience 25 / location 15 / domain 15 / growth 15) and uses it to gate which jobs get a tailored resume — critically, it excludes tailored content from the scoring input so it scores *fit*, not its own output. career-ops scores **1–5 across weighted blocks A–F** (CV match, north-star/archetype alignment, comp, culture, red flags, holistic) **plus a separate Block G legitimacy/scam assessment** that never affects the score.

**✅ Do**
- Score **role-fit separately from resume quality**, and feed it **only source profile data** (never the tailored output) — Job-Ops's discipline avoids a feedback loop where you grade your own tailoring.
- Adopt career-ops's **multi-dimensional weighted rubric** with an explicit **archetype/north-star** dimension (does this role match the user's target trajectory, not just their skills).
- Keep a **separate legitimacy signal** (Block G): ghost-job/scam/repost detection presented as signals, never accusations, never folded into the fit score.
- Use the fit score as a **gate**: only spend tailoring compute on roles above a threshold (career-ops discourages applying below 4.0/5).

**❌ Don't** conflate "am I a fit" with "is my resume good," and don't let scam/legitimacy concerns silently lower a fit score — keep them orthogonal and transparent.

---

## 14. Sponsorship data
*(H-1B / visa check for a company or role)*

**Context / learnings:** Job-Ops matches employers against sponsor registries (UK licensed-sponsor CSV). For the US, the authoritative sources are government datasets.

**✅ Do — build an enrichment step from official data (two primary sources describing two different legal steps):**
- **DOL OFLC disclosure data** — the richest, role-level source. Quarterly `.xlsx` per program/FY (each file cumulative; every file has a Record-Layout PDF). Latest confirmed **FY2026 Q1, released 2026-02-13** (~6-week lag after quarter close). Landing: `https://www.dol.gov/agencies/eta/foreign-labor/performance`. **LCA (Form ETA-9035)** = precondition for temporary work visas (H-1B/H-1B1/E-3), high volume, best "does this company sponsor, at what title/wage/worksite" signal — key fields: `EMPLOYER_NAME`, `JOB_TITLE`, `SOC_CODE`/`SOC_TITLE`, `CASE_STATUS`, `WAGE_RATE_OF_PAY_FROM/TO`, `PREVAILING_WAGE`, `PW_WAGE_LEVEL` (I–IV), `WORKSITE_CITY/STATE`. **PERM (ETA-9089)** = green-card labor cert (stronger permanent-sponsorship signal) — note OFLC issued a **revised ETA-9089, so there are two PERM files with different schemas** you must handle.
- **USCIS H-1B Employer Data Hub** — petition *outcomes* (approve/deny). Direct file pattern `https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-<YEAR>.csv` (loop years FY2009→FY2026). Aggregated per employer; **only last-4 of the EIN** is exposed → you **cannot reliably join USCIS↔DOL on tax ID**. No job titles/wages here — use it purely for approval/denial *rates*.
- Compute a **sponsorship likelihood** by joining: company → trailing-3-FY certified LCA volume + recency + matching **SOC code**/title + worksite state, weighted by USCIS approval rate. (This is exactly MyVisaJobs' "Visa Rank" method: LCA+PERM over 3 FY; "Active Sponsor" = filed in last 3 years.) SOC-matching is what turns "company sponsors" into "*this role* is sponsorable."
- Solve the hard part: **employer-name normalization** (legal entity vs DBA vs subsidiary vs typo vs post-merger rename). Since the tax-ID join is unavailable, a fuzzy-match/alias table is the single biggest data-engineering challenge here.
- **Ingest gotcha:** the USCIS/DOL **HTML pages return HTTP 403 to bots**, but the underlying **`.csv`/`.xlsx`/record-layout PDFs download fine** via direct URL — build ingest against file URLs, not the HTML. Pre-packaged mirrors exist on Kaggle (e.g. "H1B LCA Disclosure 2020–2024") and data.gov if you don't want to maintain ingest.
- **Note:** the old `flcdatacenter.com` was **discontinued 2024-07-01**; prevailing-wage lookup moved to `https://flag.dol.gov/wage-data/wage-search`. Don't hardcode dead URLs.

**❌ Don't** rely on scraped third-party sites (MyVisaJobs, H1BGrader's Chrome extension, H1BData.info) as your *primary* source — they're derived from the same gov data with **no official APIs** (scrape-only). Mirror the official DOL/USCIS files and refresh **quarterly**.

---

## 15. Job-board APIs
*(pulling latest + relevant jobs)*

**Context / learnings:** Job-Ops fans out to 10+ boards with pluggable extractors + Python JobSpy + Apify; career-ops has **78 zero-token provider modules** hitting public ATS APIs directly. Research confirms the clean path is **official public ATS JSON feeds**.

**✅ Do — prefer official/free public feeds (read-only, unauthenticated for GET; you need each company's board slug):**
- **Greenhouse**: `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` (also `/departments`, `/offices`, `/jobs/{id}`). Only the apply `POST` needs auth.
- **Lever**: `GET https://api.lever.co/v0/postings/{site}?mode=json` (filters: `location`, `team`, `department`, `commitment`, `level`, `skip`, `limit`). EU host `api.eu.lever.co`. **429 if apply-POST >2/sec** — queue/retry.
- **Ashby**: `GET https://api.ashbyhq.com/posting-api/job-board/{client}?includeCompensation=true` (structured location + comp; no server-side search/filter). **SmartRecruiters / Workable / Recruitee** also expose public postings JSON.
- **Adzuna API** (`api.adzuna.com/v1/api`, `app_id`+`app_key`, free tier, salary/trend endpoints), **USAJOBS API** (federal; requires `Authorization-Key` header **and a `User-Agent` set to your registered email** — the #1 auth-error cause), **Remotive / RemoteOK** (free JSON; Remotive ToS: 24h-delayed, must attribute, no re-publishing to other boards).
- Adopt career-ops's **pluggable provider registry** pattern (one module per source + a registry) — the real work is **normalization** across 6+ response shapes + board-slug discovery + HTML-encoded descriptions.
- Add a **liveness check** before spending eval/tailoring compute (career-ops verifies the posting is still open with Playwright).

**❌ Don't**
- Don't build your pipeline on **LinkedIn** (no public jobs API since 2015 — partner-gated only; it litigates scrapers — Proxycurl was shut down July 2025) or deprecated **Indeed** Publisher / **Glassdoor** (now routed through Indeed) APIs.
- Treat **JobSpy** (scrapes LinkedIn/Indeed/Glassdoor/Google/ZipRecruiter; Indeed scrapes best, LinkedIn throttles ~page 10 and needs residential proxies), **Workday CXS** (`POST .../wday/cxs/{tenant}/{site}/jobs` — undocumented, **`limit` caps at 20**, behind **Akamai bot management** that blocks single-IP scraping in minutes), and **Hiring.cafe** (Cloudflare-protected internal API) as fragile, gray-area fallbacks — not the backbone.
- Legal note: *hiQ v. LinkedIn* (9th Cir.) means scraping *public* data isn't a **CFAA crime**, **but the 2022 settlement still cost hiQ $500k** for breach-of-contract/trespass — so no-crime ≠ no-liability. ToS, rate limits, and bot detection still apply; anything behind a login is high-risk.

---

## 16. Agent-CLI architecture
*(Claude Code/Codex pipeline + extension/web integration)*

**Context / learnings:** This is the deepest architectural fork. career-ops's "brain" is **Markdown prompt files + skills**, executed by any AI coding CLI (Claude Code, Codex, etc.) — model/CLI-agnostic, prompts are the product. ATS-Resumaker uses **Python service calls** (direct Gemini API). Your instinct — trigger from the web extension, hand off to a Claude Code agent that fans out sub-agents (keywords, gap analysis, JD identification, competencies, company/salary/location extraction) then drafts — is exactly the modern pattern and **is achievable**.

**✅ Do — a hybrid, best-of-both architecture:**
- Keep **deterministic mechanics in code** (docx generation, scoring, fact-gate, page loop, verification) — these must be reproducible and testable, not LLM-improvised. This is ATS-Resumaker's correct instinct.
- Move **cognitive/tailoring steps into Markdown prompt files / skills** (career-ops's model) so they're versionable, model-agnostic, and runnable by a CLI.
- **Orchestration:** the browser extension scrapes the JD → POSTs to your backend → backend invokes an **agent CLI headlessly** (`claude -p` / Claude Agent SDK, or Codex CLI) that spawns **parallel sub-agents**: (a) JD keyword extraction, (b) gap analysis vs source of truth, (c) company/salary/location/role-fit extraction, (d) core-competency drafting. Results feed the **deterministic code** stages (docx build → fact gate → verification).
- Use the **Claude Agent SDK** (TypeScript or Python) to run Claude Code programmatically from your backend with tool permissions scoped to your repo/data — this is the clean bridge between "CLI approach" and "web/extension approach."
- Expose progress to the frontend via **SSE** (both Job-Ops and career-ops stream progress).

**❌ Don't**
- Don't put determinism-critical logic (scoring, fact-checking, formatting) inside free-form LLM prompts — keep those in code with tests.
- Don't couple to one CLI — abstract the "run an agent" call so Claude Code / Codex / others are swappable (see §18).

**Extension ↔ CLI bridge (your exact idea):** Extension (capture JD + company + screenshot) → backend endpoint → enqueue job → agent-CLI orchestrator runs sub-agents in parallel → deterministic build/verify → store artifact → notify frontend/extension. Yes, this is buildable and is the strongest synthesis of the three projects.

---

## 17. Consistency & determinism
*(tests + verification without losing quality)*

**Context / learnings:** career-ops has extensive tests (updater-migration, untrusted-content coverage, trust-validator, fact-gate self-tests). Job-Ops has strict API contracts + Vitest. ATS-Resumaker has a **latent no-op bug** (§5) precisely because that path lacked a test.

**✅ Do**
- Split the pipeline into **deterministic stages** (extraction round-trip, scoring, fact-gate, docx build, page loop) and **cover each with tests** — including a regression test that would have caught the `usage` NameError (assert the one-page loop actually shortens content).
- Pin LLM calls to **low temperature + structured JSON schema output** (all three constrain output with schemas) for repeatability.
- Reuse a **standardized keyword set** per JD so re-runs are consistent.
- Keep a **fact-gate self-test suite** (career-ops's `runSelfTest`) that locks in every fabrication-detection regression.
- Snapshot-test the generated document's extracted text against golden files.

**❌ Don't** chase full determinism on creative prose (you'll lose quality) — make the *guards, scoring, formatting, and fact-checking* deterministic while letting bounded creativity live in the tailoring prose, fenced by the fact gate.

---

## 18. LLM provider abstraction
*(any model / your own CLI subscription to save cost)*

**Context / learnings:** Job-Ops has the richest provider factory — Anthropic/OpenAI/Gemini/GLM/OpenRouter/Ollama/LM Studio **plus CLI-based providers: `claude_cli` (headless Claude Code), `codex`, `gemini_cli`**. career-ops is fully model-agnostic (prompts + spend-tier mapping). ATS-Resumaker is locked to Gemini API.

**✅ Do**
- Build a **provider abstraction with a `factory`** (Job-Ops's pattern): API providers *and* **CLI providers**. A CLI provider shells out to your installed `claude`/`codex`/`gemini` CLI so you use your **existing subscription** instead of paying per-token API. This is exactly your cost goal and Job-Ops already proves it works.
- Support **local models** (Ollama / LM Studio) for zero-cost/private runs.
- Add a **spend-tier** concept (career-ops: economy/standard/premium → model per provider) so cheap models do extraction and stronger models do tailoring.
- Always request **structured JSON with schema validation + retry/repair** regardless of provider.

**❌ Don't** hardcode a single provider/model (ATS-Resumaker's limitation — even the parser hardcodes a different model than config). Route everything through the abstraction.

---

## 19. Architecture

**Recommended synthesis (best of all three):**

```
┌─ Browser Extension (MV3) ──────────────┐   capture JD + company + screenshot
│  content.js scrape → background.js POST │
└──────────────┬──────────────────────────┘
               ▼
┌─ Backend API (FastAPI, Python) ─────────────────────────────┐
│  • Source-of-truth store (canonical master resume JSON/MD)   │
│  • Job ingestion: pluggable provider registry (Greenhouse/   │
│    Lever/Ashby/Adzuna/USAJOBS) + liveness check              │
│  • Sponsorship enrichment (DOL OFLC + USCIS, name-normalize) │
│  • Orchestrator → Agent CLI (Claude Agent SDK) sub-agents:   │
│      keywords │ gap-analysis │ JD/company parse │ competencies│
│  • DETERMINISTIC code stages:                                 │
│      scorer (0-100) │ semantic cosine coverage │ fact-gate   │
│      │ docx builder (python-docx) │ PDF (LibreOffice) │       │
│      one-page loop │ extraction round-trip verify            │
│  • LLM/CLI provider abstraction (API + claude_cli/codex/     │
│    ollama; spend-tier routing)                               │
│  • SSE progress stream                                        │
└──────────────┬───────────────────────────────────────────────┘
               ▼
┌─ Frontend (Next.js + React + Tailwind) ─┐   dashboard, history, analytics,
│  review/approve, download docx/pdf      │   monitoring (tokens/cost/latency)
└──────────────────────────────────────────┘
   Persistence: Postgres (derived index) + canonical files (source of truth)
```

**✅ Do**
- **Files canonical, DB derived** (career-ops). Postgres for history/analytics/monitoring (keep ATS-Resumaker's cost/latency instrumentation — it's genuinely good), canonical resume in versioned files.
- **Python backend** (best ecosystem for docx/pdf/parsing/data) + **Next.js frontend** + **MV3 extension** + **agent-CLI orchestration** via Claude Agent SDK.
- Pluggable everything: providers, job sources, resume templates, renderers.

**❌ Don't** merge deterministic and cognitive concerns; don't make the DB authoritative; don't lock to one LLM or one renderer.

---

## 20. Packaging & mobile

**✅ Do**
- **Docker Compose** for self-host (all three ship or lean this way): db + backend + frontend as ATS-Resumaker already does.
- Publish the **extension** to the Chrome Web Store; keep it thin (capture + trigger only).
- For distribution as a tool, a **CLI/npm package + skill files** (career-ops's model) is the lowest-friction way for technical users; a hosted web app for everyone else.
- **Mobile:** the web app (Next.js) should be **responsive/PWA** — installable, works on mobile browsers, good enough for review/approve/download on the go. A native app is unnecessary; a **PWA** covers mobile without a separate codebase. Server-side PDF/docx generation means the phone only needs to render/download.

**❌ Don't** attempt on-device docx/PDF generation or LLM inference on mobile — keep generation server-side and let mobile be a thin review/approve client. Don't build native iOS/Android unless you need push/offline beyond what a PWA offers.

---

## 21. Auto-apply — should you?

**Context / learnings:** Job-Ops and career-ops **both explicitly refuse to auto-apply** as a core ethical/strategic stance ("recruiters detect and blacklist automation"; "the human always clicks Submit"). Research strongly backs this.

**The verdict: don't build full auto-submit.**
- Mass auto-apply interview rates are ~**0.1%** (≈5 interviews per 5,000 applications) — generic applications get filtered.
- **Risks:** ToS violations, **LinkedIn actively detects bots and suspends accounts** (LazyApply/AIHawk are highest ban-risk), and it produces exactly the generic, high-volume applications recruiters are rejecting in 2026.

**✅ Do — build "assisted apply" instead** (the 2026 consensus, Simplify-Copilot style): autofill forms, pre-fill knockout answers, attach the tailored resume + cover letter, **stop before Submit**, human reviews and clicks. This keeps a human in the loop, respects ToS, and aligns with what 78% of hiring managers want (personalized applications).

**❌ Don't** auto-submit at volume — low ROI, reputationally damaging, and account-endangering.

---

## Appendix: the "steal this from each project" summary

| Capability | Best source | What to take |
|---|---|---|
| Native `.docx` output | **ATS-Resumaker** | python-docx with real borders/tab-stops/hyperlinks; safest format |
| Keyword-in-bullet "proof" | **ATS-Resumaker** | keywords inside quantified achievements |
| Triple-pass keyword consensus | **ATS-Resumaker** | parallel extraction + consolidation |
| Dual (deterministic + anchored LLM) scoring | **ATS-Resumaker** ⨯ career-ops | keep both; they converged on it |
| Cost/latency instrumentation | **ATS-Resumaker** | per-call token/cost/latency dashboard |
| **Hard mechanical fact-gate** | **career-ops** | block render on unsupported metric/employer/title/tool |
| Pre-draft gap analysis (`existing`/`supported`/`gap`) | **career-ops** | surface gaps, never paper over |
| Anti-AI-voice / hm-audit reviewer sim | **career-ops** | authenticity + reviewer perspective |
| Untrusted-content / prompt-injection defense | **career-ops** | JD text = data, never instructions |
| Files-canonical, DB-derived | **career-ops** | git-diffable source of truth |
| Markdown-prompt "brain" + skills | **career-ops** | model/CLI-agnostic tailoring logic |
| Zero-token public ATS provider registry | **career-ops** | Greenhouse/Lever/Ashby JSON feeds |
| Multi-provider + **CLI providers** (use your subscription) | **Job-Ops** | `claude_cli`/`codex`/`ollama` in a factory |
| Role-fit scoring isolated from tailored output | **Job-Ops** | score fit on source data only |
| Multi-board fan-out + liveness | **Job-Ops** ⨯ career-ops | pluggable sources + open-check |
| Sponsorship registry matching | **Job-Ops** (UK) → adapt US | DOL OFLC + USCIS + name normalization |
| Renderer-agnostic document model | **Job-Ops** | one model → docx/pdf/latex |
| Ligature/font extraction fix | **career-ops** | if you ever use HTML→PDF |
| Physical one-page loop | **ATS-Resumaker** (fix the bug) | render→count→trim, target by seniority |

---

### Top 5 things to fix vs. the projects you learned from
1. **Add the hard fact-gate** (career-ops) to ATS-Resumaker's aggressive rewrite — its biggest risk.
2. **Fix the one-page loop `usage` NameError** so it actually runs (add a test).
3. **Vary bullet structure** — drop "every bullet must be XYZ + a metric"; target ~50–60% quantified.
4. **Abstract the LLM/CLI provider** — unlock your own subscription + local models, don't hardcode Gemini.
5. **Make length + page target a function of seniority/JD**, not a hardcoded one page; serve US Letter alongside A4.

---

## Appendix B: Location & the full pre-advance screening checklist

> Everything a recruiter/ATS gates on *besides* the resume's keywords and prose. Most of this happens in **two waves**: an automated **knockout wave** (application-form answers, hard filters — no human involved) and a fast **human wave** (triangulation + judgment). Your system should surface these to the user and pre-fill truthful answers — it can't tailor its way past a hard gate.

### B1. Location — often a hard gate, not a soft preference

- **~43% of recruiters apply a location radius filter** (commonly "within 50 miles" of the office/job ZIP) *before* reading resumes; location is also a **ranking signal**, so being local raises your match score.
- **"Remote" ≠ location-agnostic in the US.** Fully-remote roles are almost always **remote-*restricted*** — by eligible **state of residence** (driven by real payroll **tax-nexus** cost and pay-transparency law, not arbitrariness — a single remote hire in a new state can trigger tax registration/withholding) and by **timezone** (typical ask: 2–4 hrs overlap; "must be in ET/PT" is a real posted constraint). **Hybrid** roles are searched by **office ZIP radius**, so listing only "Remote" makes you invisible to them.
- **Relocation:** bare *"Willing to relocate"* often **hurts** (reads as flight-risk / relocation-cost request); *"Relocating to [City, State] (Q3 2026)"* — specific + committed — **helps**. Listing the **target metro** is a legitimate way to pass geo filters when genuinely moving.
- **✅ Do:** present location as City + Metro + State in the body; `(Open to Remote)` or `Relocating to …` as appropriate; for past remote jobs use `Company | City, State (Remote)` to preserve the location signal. **❌ Don't:** full street address, ZIP-only, or bare "Remote".
- **Myths:** "fully remote = location irrelevant" (false — state + timezone replace commute radius); "'Open to relocation' always helps" (false — be specific).

### B2. Knockout / screening questions (the automated wave)

Binary dealbreakers on the form; a disqualifying answer auto-rejects with a template email and the recruiter **never sees you**. Can remove ~40% of a ~250-applicant pool. The common set: **work authorization; sponsorship needed (y/n); minimum years of experience; location/onsite ability; relocation; salary expectations; notice period/start date; education level; licenses/certs; travel/shift/language**. Note the "years of experience" knockout is widely mis-set — rigid thresholds can screen out up to **63% of people who could do the job** (HBS). **Your system should:** detect knockouts in the JD, pre-fill truthful answers from the source of truth, and **flag hard fails to the user** rather than silently proceeding.

### B3. Work authorization / sponsorship — heavier in 2026

The decisive question is usually **not** "authorized to work?" but **"will you need sponsorship now or in future?"** — a lawful hard filter (DOJ/OSC: declining based on future sponsorship obligation is generally not unlawful). The 2025–2026 climate hardened this: a **$100k H-1B petition fee** (Sept 2025 proclamation; later vacated June 2026 but the chilling effect persisted), FY2026 caps met, and many firms publicly paused sponsorship. For candidates needing sponsorship this is often *the* single most decisive filter — tie it directly to your §14 sponsorship enrichment so you only surface roles/companies that actually sponsor.

### B4. Employment gaps & tenure — softened, but not gone

Gaps of **6–18 months no longer concern ~76% of hiring managers** (LinkedIn 2025); the average reviewed resume now has a 3+ month gap. Job-hopping is actually **slowing** ("job hugging" in the 2025–2026 market). **Still-true risk:** *repeated* sub-1-year stints read as retention risk, and unexplained gaps *combined with other flags* invite scrutiny. Don't have the system auto-flag a single gap/short stint as disqualifying; the market shifted to **skills over tenure**.

### B5. Over/under-qualification & trajectory

"Overqualified" is a coded **retention/salary/culture risk** calc, not a compliment — and 2025–2026's flooded pools make it a frequent rejection. A senior person applying to a clearly junior role creates "intent confusion" unless the *deliberate step-back* is explained (summary is the place). Your system should let a user set a target level and warn on large level mismatches.

### B6. Salary expectations — early budget filter

Asked on the form or in the first ~10 min of the phone screen; it's a **budget gate**, and the first number **anchors** all later negotiation. Best practice: a **range**, not a single figure. Many states now ban asking **salary history** (expectation-based only). Useful for role-fit scoring (§13) and to avoid wasting tailoring on out-of-band roles.

### B7. Education / GPA / prestige — de-emphasized, with a caveat

**~85% claim skills-based hiring**; **GPA screening fell 73%→42% since 2019**; only **~18% of US postings still require a degree** (Google famously found GPA/prestige had ~zero correlation with performance after ~2 yrs). **Caveat:** ~45% of "we dropped degree requirements" is cosmetic (HBS/Burning Glass — some firms still hire <1 in 700 non-degree holders), and **regulated fields (medicine/law/engineering) still hard-require degrees**. Design: keep education, but don't over-weight GPA/school; lead with demonstrated skills. New grads still put Education/Projects high (§6).

### B8. Certifications / licenses / security clearance — hard gates

Licenses/certs are frequent knockouts where legally required. **Security clearance is a firm gate** (active > recently-held > "willing to obtain"; level matters: Secret/TS/TS-SCI/poly). Pre-cleared candidates are a large advantage. Represent these truthfully; never imply a clearance/license you don't hold.

### B9. Online-presence triangulation — now AI-automated

Recruiters (and AI screeners) **cross-check the resume against LinkedIn and public data**; **title and date mismatches get flagged and can trigger silent rejection** and cast doubt on the whole profile. **~70% of employers screen social media** (57% found something that cost a candidate the job); **60–80% of tech recruiters glance at a linked GitHub**. **Design implication:** your system should keep the generated resume **consistent with the user's LinkedIn** (titles, dates, company names) — an inconsistency you introduce by "tailoring" a title is an active liability. Consider a consistency check against a user-provided LinkedIn export.

### B10. Background / reference checks & resume-fraud detection

**~96% of US employers run a background check and ~87% run reference checks — at the offer stage** (not before first human review), verifying dates/titles/reason-for-leaving, education, work authorization. **46% of verifications show a discrepancy vs what the applicant claimed**, and **46% of HR pros say resume fraud rose since GenAI**; consequences are offers rescinded (41%) / firings (18%). This is the ultimate reason your **fact-gate (§3)** matters: anything the system fabricates will be caught downstream and is far worse than an omission.

### B11. Title match, brand, cover letters, completeness

- **Exact title match** strongly drives *surfacing* (cited ~10.6× more interviews) — reinforces §1/§8's headline-match rule.
- **Brand-name past employers** help visibility/credibility but relevant experience usually outweighs prestige (skills-based shift).
- **Cover letters are resurgent** — survey data (vendor-skewed, treat as directional): ~89% expect one, ~45% may auto-reject without one, used to read **motivation + experience-to-role connection**. Keep your cover-letter generator (career-ops/ATS-Resumaker both have one) and make it genuinely personalized, not templated.
- **Application completeness & responsiveness:** incomplete forms fail knockout logic (silent reject); **76% of recruiters report candidate ghosting** — fast follow-up matters post-screen.
- **Blind resume review** (redacting name/school/grad-year/address) + structured scoring is a growing ATS feature — another reason clean, standard, parseable structure wins.

### The throughline
Location and knockouts are **hard gates you must answer truthfully and target around** (pair with §14 sponsorship data and §13 role-fit scoring), while gaps/GPA/tenure have **softened** and **skills + consistency + verifiable specifics** have become the currency. Every downstream verification (background/reference/triangulation) rewards the same thing your fact-gate enforces: **nothing on the resume that the user can't defend and that public records won't contradict.**

> ⚠️ **Source-quality note:** many percentages in this appendix come from recruiting-SaaS / resume-vendor blogs with a commercial slant (especially cover-letter, AI-screening, and "X× more interviews" figures — treat as directional). The best-anchored findings are from SHRM, LinkedIn Workforce Confidence, ZipRecruiter Research, HBS/Burning Glass, CareerBuilder, Checkr, and government (USCIS/DOL/DOJ-OSC) sources. Also note one myth to *not* propagate: the "75%+ of resumes auto-rejected by a bot before a human sees them" claim is folklore — the real mechanism is **volume + AI stack-ranking + knockouts**, i.e. most resumes are never *surfaced*, which is different from being keyword-score-rejected (see the main doc's opening reframing).
