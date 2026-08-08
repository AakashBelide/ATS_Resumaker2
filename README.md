# ATS Resumaker 2

An accuracy-first system that tailors ATS-compliant, recruiter-ready resumes to a
specific job description — grounded strictly in a canonical source-of-truth profile,
with a hard anti-fabrication gate.

Built from a study of three prior projects (JobOps, career-ops, an earlier
ATS-Resumaker) plus 2026 research on how US ATS and recruiters actually screen.

## Documents
- [`RESUME_SYSTEM_BLUEPRINT.md`](RESUME_SYSTEM_BLUEPRINT.md) — the *what/why*: a 21-topic Do's/Don'ts playbook grounded in real ATS/recruiter behavior.
- [`TASKS.md`](TASKS.md) — the *how/when*: phased, POC-first plan with status tracking.

## Layout
```
resumaker/
  core/     # LLM provider abstraction (Claude CLI + Gemini), cost guard, schemas, profile loader
  pocs/     # Phase-1 component POCs (each independently runnable + eval)
  evals/    # eval harness
data/       # (gitignored) canonical profile + caches + gov datasets  -- holds PII, never committed
```

## Setup
```bash
# Python via uv
cd resumaker && uv sync

# Secrets (gitignored) — create .env at repo root:
#   GEMINI_API_KEY=...        # optional; Claude CLI is the default LLM engine
# Canonical profile (gitignored, holds contact PII) — create data/profile/profile.json
# (see core/schemas.py / core/profile.py for the expected shape)

# System deps
brew install --cask libreoffice     # headless DOCX -> PDF
uv run playwright install chromium  # JD scraper fallback
```

## Conventions
- **Python:** `uv` only (`uv add`, `uv run`); run modules from `resumaker/`.
- **LLM:** all calls go through `core/llm.py`. Claude CLI is the default engine
  (uses subscription); Gemini API usage is hard-capped via `core/cost_guard.py`.
- **Grounding:** everything generated must trace to `data/profile/profile.json`;
  a mechanical fact-gate blocks unsupported claims.

## Status
Phase 0 (foundations) ✅ · Task 1.1 JD scraper ✅ · Phase 1 component POCs in progress. See `TASKS.md`.

## License
Private. All rights reserved.
