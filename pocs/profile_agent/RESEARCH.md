# Profile Chat-Agent — Research & Design

Design document for a human-in-the-loop **Profile chat-agent** that (1) onboards a candidate
from a resume/LinkedIn, (2) enriches their profile through conversation, and (3) clarifies
JD↔profile gaps at match time before generating a resume — then re-matches so the fit score is
computed against the *enriched* profile.

Grounded in two external reference repos (read locally on disk) and in our own codebase. Every
claim below cites a file I actually read.

- Reference repos read: `/Users/aakashbelide/Aakash/Projects/repos/career-ops`,
  `/Users/aakashbelide/Aakash/Projects/repos/Job-Ops` (both accessible; no 404s, no WebFetch needed).
- Our repo root: `/Users/aakashbelide/Aakash/Projects/ATS_Resumaker_2`.

---

## Part A — What the reference repos do

### A.1 career-ops (`repos/career-ops`) — the model for conversation + honesty gates

career-ops is a **Markdown-mode + Node `.mjs`-script** system: an LLM (via a router skill,
`.claude/skills/career-ops/SKILL.md`) loads one of ~60 mode files under `modes/`; the `.mjs`
scripts are deterministic, mostly **zero-LLM** helpers. (Note: `followup-seed.mjs`, despite its
name, is about recruiter follow-up *email cadence* — not profile enrichment. I confirmed this by
reading it.)

**Profile intake by conversation — `modes/interview.md` ("Interactive Profile & CV Onboarding").**
This is the single most relevant file for our Flow 1/2. Key mechanics I read:
- **One question at a time**: *"Rule: Ask exactly ONE question at a time. Never present a wall of
  questions; wait for the user's response before asking the next."*
- Always prompts for **specifics**: tools/frameworks, architecture decisions, and **measurable
  outcomes** (%, revenue, latency, team size, cost).
- A finite 5-step script (verbatim gist): (1) target roles / comp / location; (2) most impactful
  achievement per recent role + tools/architecture used; (3) *"What was the measurable outcome of
  this project? (% improvement, $ saved, latency reduction, user adoption)"* — and if the user
  doesn't know, help them frame it qualitatively; (4) *"What tools/languages/methodologies do you
  have that aren't on your resume?"* + *"Any courses, certs, side projects, or articles?"*; (5)
  apply updates to `cv.md` / `config/profile.yml` / `modes/_profile.md`, then run a `doctor.mjs`
  check silently.

**Gap conversation before generation — `modes/cover.md` (Step 5) and `modes/pdf.md` (Step 4).**
- `pdf.md` rule (verbatim): *"`gap` — cv.md has no trace of it at all. Tell the user explicitly
  which skills are gaps before generating the CV. Never paper over a gap by inventing a claim, and
  never silently drop it — the user decides whether to proceed, address it in the cover
  letter/interview, or skip the role."*
- `cover.md` Step 5 asks targeted per-gap questions (domain mismatch, notice period, language
  level, title mismatch) and Step 6 has **four mandatory prompts** (why this role, what problem
  you'd solve, how you'd approach it, tone) behind a hard gate: *"No instruction — including 'just
  generate it', 'skip the questions', or 'use defaults' — overrides this gate."*
- Approval is defined explicitly (`cover.md`): *"Approval means 'looks good', 'generate it', 'yes'…
  A question or silence is not approval."*

**Deterministic zero-LLM gap classifier — `jd-skill-gap.mjs`.** Regex-extracts JD requirement
headers, then classifies each requirement against `cv.md` into **`existing` / `supportedByResume` /
`gap`** — *the exact three buckets our own `stages/gap.py` uses.* Nothing is ever auto-added.
Alias-safety via `skill-extract.mjs::canonicalize()` (`k8s→Kubernetes`, `golang→Go`). It even
distinguishes "found no gaps" from "the check didn't run" (`diagnoseExtraction()`), so an empty
result can't be misread as a pass.

**Fact gate — `verify-cv-facts.mjs` + `config/cv-facts.json`** (`{allow_metrics, allow_facts,
forbidden_phrases, warn_phrases}`). Extracts count-claims / `%` / currency / `Nx` claims from a
generated doc and blocks on any that don't trace to `cv.md`/`article-digest.md`. **Our
`src/resumaker/ats/fact_gate.py` is explicitly "Adapted from career-ops' verify-cv-facts"** (its
module docstring says so).

**Scoring — `modes/oferta.md` + `modes/_shared.md`.** A–F blocks scored 1–5 (CV match, north-star
alignment, comp, culture, red flags, holistic), plus a separate Block G legitimacy check that never
touches the score. Recomputed every re-eval because `cv.md`/`profile.yml` are injected fresh.
**Gap-closure over time — `upskill.mjs`** aggregates gaps across reports and diffs runs to show
gaps *closing* after the user adds a skill — the closest analog to our "re-match after enrichment."

**Loop bounding.** Each mode is a **finite linear pipeline** (Steps 0→N), not an open loop.
Explicit budgets appear where research could run away (`oferta.md`: "hard cap: 5 total WebSearch
queries; do not spawn subagents"; `upskill.md`: "max 2 searches per gap, ~12 per run").

**Profile schema — `config/profile.yml`.** `candidate{…}`, `target_roles.archetypes[]`,
`narrative{headline, exit_story, superpowers[], proof_points[]{name,url,hero_metric}}`,
`compensation`, `location{visa_status, needs_sponsorship, …}`, plus an evidence store
`article-digest.md` (`## Name — tagline` / **Hero metrics** / **Architecture** / **Key decisions** /
**Proof points**).

**Borrow:** one-question-at-a-time interview; the verbatim metric/hidden-skill probes; the
`existing/supportedByResume/gap` classifier (we already have it); explicit "tell the user the gaps
before generating"; confirm-before-write with an explicit definition of approval; bounded budgets;
the evidence/proof-point store idea.
**Skip:** the Markdown-mode routing machinery, the `.mjs` proliferation, the freeform `cv.md` as
source of truth (we use structured `profile.json`).

### A.2 Job-Ops (`repos/Job-Ops`, dakheera47) — the model for the chat runtime + scorer

TypeScript monorepo; the relevant app is `orchestrator/`. There is **no dedicated profile
chat-agent**; the closest analog is **"Ghostwriter,"** a per-job advisory chat.

**Resume parsing — `orchestrator/src/server/services/design-resume/import-file.ts`.** JSON uploads
validate directly against the Reactive-Resume v5 schema (no LLM); PDF/DOCX are text-extracted
locally then sent to an LLM for structured extraction. **No LinkedIn import anywhere.** The
extraction `SYSTEM_PROMPT` is a strict zero-invention contract (verbatim): *"Extract only
information explicitly present… Do not guess, infer, summarize, embellish, or invent missing
values… If a field is unknown, use an empty string/array/placeholder."* One-shot, template-shaped
(it embeds the empty target JSON and says "Use this exact target shape and keys").

**Profile schema — `shared/src/types/settings.ts::ResumeProfile`** (Reactive Resume v5):
`basics{name,headline,email,phone,location,profiles[]}`, `sections.summary`,
`sections.skills.items[]{name, level:number, keywords[], description}`,
`sections.experience.items[]{company,position,location,date,summary}`, `projects`, `education`,
etc. **Critically: there is no structured `metric` or `evidence` field** — achievements live only
as free-text HTML inside `summary`/`description`. Skills are a category name + keyword list +
numeric proficiency. *(This is a shape we improve on: our `profile.json` stores atomic `metrics[]`
and `skills_used[]` per bullet — see B.1.)*

**No enrichment probing.** I confirmed (via the subagent's search) there is **no follow-up /
interview / clarify feature**. The only assist is `ai-field-suggestion.ts` — a single-field rewrite
on demand ("edit only the active field; keep the user in the loop"). So structured probing for
metrics/tech/stakeholders is a **gap we are filling**, not something to copy.

**No JD-vs-profile gap module, no pre-generation clarification.** `shared/src/job-matching.ts`
(despite the name) is only dedup + location matching. Gaps are handled softly inside the
Ghostwriter system prompt (`shared/src/prompt-template-definitions.ts`, verbatim): *"Use only the
provided job and profile context… Do not claim actions were executed. You are read-only and
advisory. If details are missing, say what is missing before making assumptions."* The scorer emits
`jobBrief.missing_or_unclear` — but those are gaps **in the JD**, not the candidate.

**Chat loop — `orchestrator/src/server/services/ghostwriter.ts`.** Single-shot per user message:
exactly one `llm.callJson()` with a strict `{response: string}` schema — **no tools, no ReAct loop,
so no infinite-loop risk by construction.** Loop safety: history windowed to `.slice(-40)`; a DB
unique index enforces **one active run per thread**; `AbortController`-based cancellation; statuses
`running|completed|cancelled|failed`. No slash commands — instead a **git-like branching message
tree** (`parentMessageId`/`activeChildId`/`replacesMessageId`/`version`) supporting
regenerate/edit/switch-branch.

**Scorer — `orchestrator/src/server/services/scorer.ts` + `scoringPromptTemplate`** (verbatim
rubric): *Skills 0-30, Experience 0-25, Location 0-15, Domain 0-15, Growth 0-15 → 0-100.* This is
essentially the same dimension set as our `stages/role_fit.py` (`skills/experience/seniority/
domain/growth`). Re-scoring is **implicit**: the profile is re-read per pipeline run (30-min cache),
so editing the base resume yields new scores next run — there is **no explicit "re-score after
enrichment" trigger tied to a chat step.** That explicit trigger is another gap we fill (Flow 3).

**Borrow:** the strict zero-invention extraction prompt; the strict JSON output contract; the
one-active-run lock + bounded history window (loop safety); the branching message tree (nice-to-have
later); the 0-100 weighted scorer (we already have an equivalent).
**Skip:** the RxResume schema (ours is richer for metrics/evidence); the "no gap analysis / no
probing" posture — those are precisely the features we add.

### A.3 One-line synthesis

career-ops shows **how to converse honestly** (one question at a time, deterministic gap buckets,
hard fact gate, never auto-add). Job-Ops shows **how to run the chat safely and score fit**
(single-shot turns, one-run lock, 40-msg window, 0-100 weighted rubric). Our system already has
career-ops's gap classifier (`gap.py`) and fact gate (`fact_gate.py`) and Job-Ops's scorer
(`role_fit.py`); what's missing — and what this POC adds — is the **conversational layer** that
turns real user assertions into profile updates and re-runs the match.

---

## Part B — Our codebase (what we reuse)

### B.1 Profile schema & persistence

- `src/resumaker/persistence/profile.py` — canonical loader. `load_profile()`/`load_preferences()`
  (DB-backed dual-mode, auto-migrating the legacy JSON on first read), `save_profile(data)` /
  `save_preferences(data)` (write to DB + `invalidate()` caches). Fact-gate feeders: `all_metrics()`,
  `all_employers()`, `all_titles()`, `all_skills()`, plus `equivalence_map()`, `facts_allowlist()`,
  `profile_text()` (the flattened grounding blob used by gap/fit prompts).
- `data/profile/profile.json` — actual shape (keys read):
  `contact{name,email,phone,location,work_model_note}`, `links`, `work_authorization{status,
  needs_sponsorship_future,note}`, `target_archetypes[]`, `summary`,
  `experience[]{id,title,organization,location,start_date,end_date,is_current,
  bullets[]{text, metrics[], skills_used[]}}`,
  `projects[]{id,title,organization,date,url,bullets[]}`, `education[]`, `skills{category:[…]}`,
  `certifications[]`, `awards[]`, `languages[]`, `equivalence_map{owned→[equivalents]}`,
  `facts_allowlist{employers[],titles[],headline_metrics[],forbidden_phrases[]}`.
  **Key advantage over both reference repos: metrics and skills are stored *atomically* per bullet
  (`metrics[]`, `skills_used[]`)** — the enrichment agent writes into these, which is exactly what
  the fact gate reads.
- `Resources/master_resume.json` — older/secondary shape: `contact_info, summary, work_experience,
  projects, education, certifications, skills`. Per `profile.json._meta`, `cv.md`/`profile.json` is
  the source of truth and this is "stale; used for atomic metric structure only." Our onboarding
  intake (Flow 1) writes the canonical `profile.json`; keeping `master_resume.json` in sync is a
  best-effort secondary write.

### B.2 Gap & fit stages (the report.json contract)

- `src/resumaker/stages/gap.py` — `analyze_gaps(jd) -> GapReport`. Each `GapItem` =
  `{requirement, status ∈ {existing, supportedByResume, gap}, evidence, substitution}`. The LLM must
  cite profile evidence; `_verify_evidence()` re-checks it against the profile and **downgrades any
  unverifiable claim back to `gap`** — the model cannot invent a match. `substitution` bridges a gap
  only via the curated `equivalence_map`.
- `src/resumaker/stages/role_fit.py` — `score_fit(job, gap) -> FitScore`.
  `_deterministic_coverage()` weights gap items: **`existing`=1.0, `supportedByResume`=0.7,
  `gap`+substitution=0.5, `gap`=0.0**, averaged over items ×100. Final = `0.5*det + 0.5*llm` with
  the LLM anchored to within ±25 of `det`. **This is the mechanism that makes re-match raise the
  score** (see Flow 3): asserting real evidence flips items from `gap`→`supportedByResume`/`existing`,
  lifting `det`, lifting `final`.
- `src/resumaker/domain/schemas.py` — `GapItem`, `GapReport`, `FitScore`, and `PipelineResult`
  (the shape serialized to `report.json`: `job, keyword_set, gap, fit, sponsorship, decision,
  resume, fact_gate, ats, …`).
- `src/resumaker/ats/fact_gate.py` — `verify_resume(content) -> VerifyReport`; `ungrounded_metrics()`.
  `_profile_metric_set()` = curated `all_metrics()` ∪ every number appearing anywhere in
  `profile_text()`. This is the non-bypassable anti-fabrication gate the agent must never route
  around — it must instead *make the fact real in the profile* (the enrichment path).

### B.3 LLM provider (what the agent drives)

- `src/resumaker/providers/llm/base.py` — `LLMProvider.complete()` and the shared
  `complete_json()` (appends a strict-JSON instruction, retries with a repair nudge).
- `src/resumaker/providers/llm/claude_cli.py` — `ClaudeCLIProvider`: shells `claude -p <prompt>
  --output-format json --max-turns 1 --model <m> --tools ""` (tools disabled → pure text gen),
  with retries/backoff and cost logging. **Single-turn by design** — the *conversation* is driven
  by us re-invoking `complete_json()` with accumulated history in the prompt, exactly like Job-Ops's
  Ghostwriter (one `callJson` per user message). No streaming tool loop → no infinite-loop surface.
- `src/resumaker/providers/llm/registry.py` — `get_provider(name=…, model=…)` factory with
  transparent caching + fallback. The agent calls this; it stays engine-agnostic.

### B.4 How a run/generation is triggered

- `src/resumaker/pipeline/orchestrator.py` — `run_pipeline(url, *, job, keyword_set, gap,
  run_id, match_only, gate, …)`. Two facts we exploit:
  1. **`match_only=True`** runs keywords/gap/sponsorship/fit/apply and stops before resume — this is
     the "re-match" call for Flow 3 (cheap, no resume yet).
  2. **`keyword_set` and `gap` are reusable inputs** — the generation path normally passes the prior
     match's `gap` to skip re-analysis. For Flow 3 we do the opposite: **force a fresh `gap` (pass
     `gap=None`) so it re-classifies against the enriched profile**, then generate.
- `apps/api/routers/runs.py` — `POST /v1/runs` (`start_run`) mints/reuses a `run_id` and submits to
  the job queue; a generation **reuses the match's `run_id`** so the tailored resume lands in the
  same run folder and overwrites `report.json`. `report.json` is the source of truth for what a run
  has. This is the endpoint the "Generate resume" button hits today.

### B.5 The async human-in-the-loop pattern to copy (onboarding)

- `src/resumaker/onboarding/service.py` + `apps/api/routers/onboard.py` — the template for our
  agent's lifecycle. A DB row is the source of truth; a `ThreadPoolExecutor` runs work off the
  request thread; **states** `running | needs_input | resolved | drafted | unresolved | killed |
  stopped | error` (`OnboardState` in `src/resumaker/domain/ingestion.py`); an `events[]` timeline
  (`OnboardEvent{stage,status,detail,ts}`) the frontend polls; `provide_input(run_id, answer)`
  resumes a `needs_input` pause; `stop(run_id)` is the manual kill. API surface: `POST /v1/onboard`,
  `GET /{id}`, `POST /{id}/input`, `POST /{id}/stop`. **Our profile agent mirrors this exactly.**
- Loop caps to copy: `pocs/agentic_onboard/orchestrator.py` — `MAX_TURNS=60`, `TIME_LIMIT_S=2400`
  (40 min), `BUDGET_USD=5.00`; the onboarding settings expose `onboard_max_turns` /
  `onboard_time_limit_s`. The POC CLI (`pocs/agentic_onboard/cli.py`) is the shape to imitate:
  subcommands `resolve` / `provide-input` / `watch` / `stop`, writing `runs/<id>/status.json`.

### B.6 Existing enrichment infra (already anti-fabrication)

- `src/resumaker/enrichment/manager.py` — **`update_profile_fact(path, value, reason, source)`**:
  folds a fact into `profile.json` at a nested key path, logs old→new+reason to an append-only
  JSONL, and `invalidate()`s the cache. Docstring: *"NEVER call this to fabricate — only to record
  real owner-provided facts."* Also `add_house_rule()` / `house_rules_prompt()` (learned
  corrections injected into stage prompts) and `record_enrichment()` (audit log). **Flow 2's writes
  go through this function** — we do not invent a new writer.
- `src/resumaker/enrichment/proposals.py` (RA.3) — already mines tracked jobs' `report.json` gap
  reports into two signals with the exact honesty split we need:
  - **`have_but_unlisted`** — requirements judged `supportedByResume` (evidence exists, just not a
    named skill) → safe to surface as "you have this; consider listing it."
  - **`recurring_gaps`** — true `gap`s → surfaced **for awareness only**; the owner adds one *only
    if they actually have it*. *"Proposing to 'add' a genuine gap would be fabrication."*
  This is the seed bank for Flow 3's talking points.

---

## Part C — The design (three flows + loop control + layout + guardrails)

Overarching principle, borrowed from both repos and our own gate: **the agent is a scribe, not an
author.** The LLM proposes structure and asks questions; a fact only enters `profile.json` when the
**user asserts it**, via `enrichment.manager.update_profile_fact()`, which is audited. Nothing the
agent writes can bypass `ats/fact_gate.py`.

All three flows share one runtime (`agent.py`, below): a DB/JSON-backed run with states
`running | needs_input | done | stopped | error`, an `events[]` timeline, single-turn Claude-CLI
calls with accumulated history, and slash-command handling. This mirrors `onboarding/service.py`.

### Flow 1 — Onboarding intake (resume + optional LinkedIn PDF → profile.json)

**Steps.**
1. **Extract text locally** from the uploaded resume PDF/DOCX (reuse
   `stages/resume/render_pdf.extract_text` for PDFs) and, if provided, the LinkedIn "Save to PDF"
   export. No LLM for text extraction.
2. **Structured parse (one-shot, zero-invention).** Call `get_provider("claude", model="sonnet")
   .complete_json()` with a Job-Ops-style strict prompt that emits **our** `profile.json` shape
   (`contact/links/summary/experience[bullets{text,metrics,skills_used}]/projects/education/skills/
   …`). Verbatim guardrail lines (adapted from Job-Ops `import-file.ts`): *"Extract only
   information explicitly present. Do not guess, infer, embellish, or invent. If a field is unknown,
   leave it empty. Copy dates, employers, and titles exactly."* Populate `metrics[]` only with
   numbers literally present in the source; populate `skills_used[]` only with tools named in that
   bullet.
3. **Thin-parse detection → ask the user to fill.** After parsing, run cheap completeness checks
   (deterministic, no LLM): any experience with 0 bullets; any bullet with `metrics == []` that
   contains an outcome verb (improved/reduced/increased); missing `summary`; `skills` groups < N;
   missing `work_authorization`. For each thin spot, enter `needs_input` with **one question at a
   time** (career-ops `interview.md` discipline), e.g. *"Your Granite role has no measurable
   outcomes listed — what changed because of the NL2SQL workflow (a %, $, time saved, or user
   count)?"* The user's answer is written via `update_profile_fact(["experience", i, "bullets", j,
   "metrics"], [...])`.
4. **Build/merge.** Write canonical `profile.json` via `save_profile()`; best-effort secondary write
   to `Resources/master_resume.json` (structural mirror). Seed `facts_allowlist.employers/titles`
   from the parsed structured fields so the fact gate recognizes them.
5. **Basic preference questions** (short, batched-as-a-form is acceptable here since they're
   objective, not evidential). Writes go to `preferences` via `save_preferences()`.

**Exact preference questions (Flow 1):**
1. Target roles / archetypes? (e.g. AI Engineer, ML Engineer, GenAI/Agentic Engineer, Data
   Scientist, Data Engineer) — writes `target_roles` / mirrors `profile.target_archetypes`.
2. Seniority you're targeting? (intern / new-grad / mid / senior / staff).
3. Work model? (onsite / hybrid / remote) and current base location.
4. Relocation: open to it? Which metros?
5. Work authorization + sponsorship: do you need visa sponsorship now or in the future?
   (drives `work_authorization.needs_sponsorship_future` + the sponsorship knockout).
6. Compensation target range (and hard minimum), currency.
7. Any hard "no" filters? (industries/companies to exclude, e.g. no security roles per the owner's
   stated preference).
8. Style rules to remember? (e.g. "no em-dashes", "combine the Bajaj roles", "inline location") —
   stored as **house rules** via `enrichment.manager.add_house_rule(scope="tailor", …)`.

### Flow 2 — Profile enhancement chat (free text / JSON dump / probe answers → profile updates)

**Input modes.** (a) free-text ("At Granite I also stood up the Qdrant vector store and cut
retrieval latency ~40%"); (b) a big JSON/text dump (an old resume, a brag doc, a project write-up);
(c) answers to the agent's probes.

**Turn loop (single-shot, career-ops honesty + Job-Ops runtime).**
1. The agent sends `complete_json()` an "analyze this user input against the current profile" prompt
   → returns a list of **proposed updates**, each `{path, value, kind ∈ {add_skill, add_metric,
   add_bullet, edit_summary, add_project, set_pref, add_house_rule}, source_quote, confidence}`. The
   `source_quote` **must** be a span from the user's own message; a proposal with no user-provided
   quote is rejected (anti-fabrication — see C.5).
2. The agent shows the diff and asks to confirm ("I'll add `Qdrant` to RAG & Generative AI and a
   bullet on the Granite role: '…reduced retrieval latency ~40%…'. Apply? `/skip` to drop it.").
   **Approval is explicit** (career-ops rule): a question or silence is not approval.
3. On confirm, write via `update_profile_fact(...)` / `save_preferences(...)` /
   `add_house_rule(...)`; each write is audited by `record_enrichment()`.
4. When the agent has nothing thin left to probe (or the user says `/done`), it summarizes what
   changed and exits.

**Probing-question bank (seeds the agent), grouped by theme.** The agent picks the *fewest*
questions that target actual thin spots; it never asks all of these.

- **Impact / metrics** (career-ops Step 3):
  - "What measurably changed because of this project — a %, $, time saved, latency, throughput, or
    user/record count?"
  - "Before vs after: what was the baseline, and what did it become?"
  - "How many people/teams/records/requests did it touch?"
  - "If you can't measure it, how would you frame the impact qualitatively (e.g. 'enabled 12 devs to
    ship 3× faster')?"
- **Tech stack** (career-ops Step 4):
  - "Which languages, frameworks, DBs, and cloud services did you actually use here?"
  - "What tools do you know that aren't on your resume yet (side projects, coursework, POCs)?"
  - "Model/framework versions or specifics worth naming (LangGraph, MCP, Qdrant, Databricks…)?"
- **Role / scope**:
  - "What was your exact title and level, and how big was the team?"
  - "Were you the builder, the lead/architect, or the reviewer?"
  - "End-to-end ownership or one slice? Which slice?"
- **Stakeholders / communication**:
  - "Who used or depended on this (internal teams, external customers, executives)?"
  - "Did you present results, write docs, or run demos? To whom?"
  - "Any cross-functional collaboration (PM, data, security, infra)?"
- **Business domain**:
  - "What business problem did this solve, and in what domain (fintech, telecom, healthcare…)?"
  - "What domain terms or regulations were involved (fraud, delinquency, HIPAA, KYC)?"
- **Achievements / recognition**:
  - "Any awards, promotions, patents-filed, publications, or talks?"
  - "Certifications or courses completed recently?"
  - "Anything you're proud of that never made it onto a resume?"

### Flow 3 — Match-time gap clarification (the keystone: talk → re-match → generate)

**When it fires.** On the report page, when the user clicks **Generate resume** and the run's
`report.json` has (a) any `gap.items[].status == "gap"` or (b) any `have_but_unlisted` signal from
`enrichment/proposals.py`, the UI intercepts with a nudge dialog:

> **"Before we generate — want to talk to the resume agent about {N} gaps and {M} things you may
> already have?** Clarifying lets us re-compute your fit score against your real background, so the
> tailored resume is more accurate. [Talk to agent] [Generate anyway]"**

**Agent conversation (focused on real gaps, never fabrication).**
1. Seed the talking points from the report: `gap` items (JD wants it, profile has no evidence) and
   `supportedByResume`/`have_but_unlisted` items (evidence exists, not named). For each `gap`, the
   agent asks a **have-you-actually-done-this** question — never "should we add this?":
   *"The JD wants Kafka. I don't see it in your profile. Have you used Kafka (or an equivalent like
   Kinesis/PubSub) on real work? If yes, where and what did you build?"*
2. If the user asserts real evidence → write it via `update_profile_fact()` (a new
   `skills_used[]` entry, a bullet, or an `equivalence_map` bridge if it's an honest substitution).
   If the user says "no / never" → leave it a gap; optionally note it as a `recurring_gap` for the
   awareness list. The agent explicitly **will not** add a gap the user can't back
   (`proposals.py` rule, verbatim: *"proposing to 'add' a genuine gap would be fabrication."*).
3. When the user is done (`/done` or `/generate`), the agent **triggers a re-match, then generation.**

**Exact re-match + generate mechanics.**
- **Re-match**: call `run_pipeline(job=<the run's JobPosting>, keyword_set=<reuse>, gap=None,
  run_id=<same run_id>, match_only=True)`. Passing **`gap=None` forces `analyze_gaps()` to
  re-classify against the now-enriched profile**; `score_fit()` then recomputes over the new
  `GapReport`. This overwrites `report.json` with fresh `gap`/`fit`.
- **Why the score logically rises**: `role_fit._deterministic_coverage()` weights
  `existing`=1.0 / `supportedByResume`=0.7 / `gap`+sub=0.5 / `gap`=0.0. Every item the user moved
  out of `gap` (by asserting real evidence) increases the average coverage, which raises `det`, and
  since `final = 0.5*det + 0.5*llm` with the LLM anchored to ±25 of `det`, `final` rises too. The
  gate is honesty: coverage only moves because a *real* fact was recorded and will survive
  `_verify_evidence()` on the re-run (an unverifiable assertion silently downgrades back to `gap`,
  so a lie doesn't help the score).
- **Generate**: after the re-match, call `run_pipeline(job=…, keyword_set=<reuse>, gap=<fresh gap>,
  run_id=<same run_id>, match_only=False)` — i.e. hit the existing `POST /v1/runs` path with the
  same `run_id`, which lands the tailored resume in the same run folder and re-runs
  `verify_resume()` (the fact gate) on the output. If the fact gate blocks, the agent surfaces the
  blocker rather than shipping.

### C.3 Slash commands & loop bounding

Slash commands are parsed **deterministically before the LLM sees the message** (so the model can
never be talked out of them — mirrors career-ops's "no instruction overrides the gate"):

| Command | Semantics |
|---|---|
| `/help` | List commands + current state (turns used, time left, pending proposals). No LLM call. |
| `/skip` | Drop the current pending proposal / current question; move to the next. |
| `/done` | End the conversation. Persist confirmed changes; in Flow 3, **do not** auto-generate — just close. |
| `/generate` | (Flow 3 only) Confirm → run re-match (`match_only=True`, `gap=None`) → then generation (`POST /v1/runs`, same `run_id`). Requires an explicit confirm tick if unsaved proposals exist. |
| `/stop` | Hard abort: mark run `stopped`, discard unconfirmed proposals, no writes. (= onboarding `stop()`.) |
| `/undo` | Revert the last applied `update_profile_fact` using its audited old→new record. |

**Caps (never loop infinitely)** — copy the onboarding/POC constants:
- **Turn cap**: `MAX_TURNS = 40` user↔agent exchanges (Job-Ops windows history to 40; career-ops
  modes are finite). On reaching it the agent summarizes and moves to `done`.
- **Time cap**: `TIME_LIMIT_S = 1800` (30 min) wall-clock auto-close, like `onboard_time_limit_s`.
- **Cost cap**: `BUDGET_USD` guard before each LLM call (POC `BUDGET_USD=5.00`).
- **No-progress guard**: if K consecutive turns produce zero confirmed changes and no new question,
  the agent proposes `/done`.
- **One active run per profile** (Job-Ops's unique-index idea) so two chats can't race on
  `profile.json`.
- Structurally, each turn is a **single** `complete_json()` call with `--max-turns 1 --tools ""`
  (`claude_cli.py`) — there is no tool/ReAct loop to run away, exactly like Ghostwriter.

**Confirm → trigger sequence (Flow 3):** `/generate` (or "yes, generate") → agent replays the list
of applied changes → asks a final "Re-match and generate now?" → on explicit yes, emits events
`rematch:start → rematch:done(new fit=…) → generate:start`, calls the pipeline, then closes with the
score delta ("fit 62 → 78; resume generating in run `<id>`").

### C.4 Module / file layout under `pocs/profile_agent/`

Mirrors `pocs/agentic_onboard/` so it's CLI-drivable first, wired into API/web later.

```
pocs/profile_agent/
  RESEARCH.md            # this document
  README.md              # how to run the CLI POC (to be written when code lands)
  agent.py               # the single runtime: run states, events, turn loop, slash-command parsing,
                         #   caps; drives get_provider("claude").complete_json() with history.
  prompts.py             # system + task prompts: intake-extract, analyze-user-input, gap-probe,
                         #   confirm-diff. All carry the zero-invention guardrail block.
  questions.py           # the preference questions (Flow 1) + the probing-question bank (Flow 2),
                         #   as data the agent selects from.
  intake.py              # Flow 1: text extraction + one-shot structured parse + thin-parse detection.
  enhance.py             # Flow 2: analyze input -> proposals -> confirm -> update_profile_fact.
  gapchat.py             # Flow 3: seed talking points from report.json + proposals.py; re-match; generate.
  store.py               # run state persistence: runs/<id>/status.json (CLI) with a DB seam later.
  cli.py                 # subcommands: intake <resume.pdf> [--linkedin x.pdf] | enhance <run_id>
                         #   | gapchat <report_run_id> | say <run_id> "<msg-or-/command>"
                         #   | watch <run_id> | stop <run_id>   (shape copied from agentic_onboard/cli.py)
  runs/                  # per-run artifacts (git-ignored)
```

**Reused, not reimplemented:** `persistence.profile` (load/save), `enrichment.manager`
(`update_profile_fact`, `add_house_rule`, `record_enrichment`), `enrichment.proposals`
(`have_but_unlisted`/`recurring_gaps`), `stages.gap.analyze_gaps`, `stages.role_fit.score_fit`,
`pipeline.run_pipeline`, `providers.llm.get_provider`, `ats.fact_gate.verify_resume`.

**Later wiring (no UI needed for the POC):**
- API: a new `apps/api/routers/profile_agent.py` mirroring `onboard.py` — `POST /v1/profile-agent`
  (start, with `mode: intake|enhance|gapchat` + optional `report_run_id`), `GET /{id}` (poll state +
  events + pending proposals), `POST /{id}/say` (a message or slash command; the "input" analog of
  `onboard/{id}/input`), `POST /{id}/stop`. `/generate` inside a `gapchat` run calls the existing
  `POST /v1/runs` path with the shared `run_id`.
- Web: a chat panel on the report page and a "Profile" page; the Generate button's `onClick` first
  checks `report.gap` + proposals and, if non-empty, opens the nudge dialog described in Flow 3
  before POSTing to `/v1/runs`. The backend contract is identical whether driven by CLI or web.

### C.5 Anti-fabrication guardrails

Ties directly into the existing fact-gate philosophy (blueprint §3; `ats/fact_gate.py`;
`enrichment/proposals.py`). The agent adds **only what the user asserts** — it never invents metrics,
tech, employers, or titles.

1. **User-quote requirement.** Every proposed profile write must carry a `source_quote` that is a
   verbatim span of the user's own message (or the uploaded resume for Flow 1 intake). A proposal
   with no user-provided source is dropped before it's ever shown. (career-ops: *"Never fabricate.
   Confirm before write."*; Job-Ops extraction: *"Do not guess, infer, embellish, or invent."*)
2. **Explicit confirmation.** No write happens without an explicit user "yes/apply" — a question or
   silence is not approval (career-ops `cover.md` rule). Writes go through
   `enrichment.manager.update_profile_fact()`, which records old→new+reason to the audit log
   (`record_enrichment`), so every change is reversible (`/undo`) and traceable.
3. **Gaps are surfaced, never papered over.** For a true `gap`, the agent asks "have you actually
   done this?" — it never proposes "add X." If the user says no, it stays a gap (`proposals.py`:
   *"proposing to 'add' a genuine gap would be fabrication."*).
4. **The fact gate is the backstop.** After Flow 3 generation, `ats/fact_gate.py::verify_resume()`
   runs unchanged: any metric/employer/title on the resume that doesn't trace to `profile.json` is a
   hard block, and `facts_allowlist.forbidden_phrases` still hard-block. Because the agent only ever
   makes a fact *real in the profile* (never routes around the gate), a legitimately-added metric
   passes and a fabricated one is caught either at proposal time (no user quote) or at gate time.
5. **Re-match honesty.** The score can only rise via `_deterministic_coverage`, and coverage only
   rises when `analyze_gaps` re-classifies an item — which its `_verify_evidence()` step will do
   *only if the newly written evidence actually appears in the profile*. So an unbacked assertion
   cannot inflate the score; it silently downgrades back to `gap` on the re-run.
6. **Honest substitutions stay gated.** A `gap`→bridge is allowed only through the curated
   `equivalence_map` (blueprint §9), and only after the user confirms the equivalence — the agent
   never invents equivalences freely.

---

## Appendix — files I read (for traceability)

**Reference repos:** `repos/career-ops/{modes/interview.md, modes/cover.md, modes/pdf.md,
modes/oferta.md, modes/_profile.template.md, jd-skill-gap.mjs, skill-extract.mjs, verify-cv-facts.mjs,
followup-seed.mjs, upskill.mjs, .claude/skills/career-ops/SKILL.md, config/profile.yml}`;
`repos/Job-Ops/{shared/src/prompt-template-definitions.ts, shared/src/job-matching.ts,
shared/src/types/settings.ts, shared/src/types/chat.ts, orchestrator/src/server/services/{ghostwriter.ts,
scorer.ts}, orchestrator/src/server/services/design-resume/{import-file.ts, ai-field-suggestion.ts}}`.

**Our codebase:** `src/resumaker/persistence/profile.py`, `data/profile/profile.json`,
`Resources/master_resume.json`, `src/resumaker/stages/{gap.py, role_fit.py}`,
`src/resumaker/domain/{schemas.py, ingestion.py}`, `src/resumaker/ats/fact_gate.py`,
`src/resumaker/providers/llm/{base.py, claude_cli.py, registry.py}`,
`src/resumaker/pipeline/orchestrator.py`, `apps/api/routers/{runs.py, onboard.py}`,
`src/resumaker/onboarding/{service.py, agent_runner.py}`,
`src/resumaker/enrichment/{manager.py, proposals.py}`,
`pocs/agentic_onboard/{cli.py, orchestrator.py}`, `RESUME_SYSTEM_BLUEPRINT.md` (§3, §5, §9, §12–13).
