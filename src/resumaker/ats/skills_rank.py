"""Deterministic, grounded skills selection (Task 1.11c).

Fixes the recurring failure where the LLM regroups skills and silently DROPS
grounded, JD-relevant tools (happened twice: Snowflake/Airflow, then
Docker/Kubernetes/Terraform). This selects from the candidate's real profile
skills only (never fabricates), ranks them by JD relevance, guarantees the
role-standard stacks survive (house-rule `skills-completeness`), and returns a
categorized dict - reproducibly, with no LLM.
"""
from __future__ import annotations

import re

from resumaker.domain import JobPosting, KeywordSet
from resumaker.persistence import profile as prof

# Grounded tools that MUST survive for an AI/ML/eng role even if the JD omits the
# exact word (recruiter-searched). Included ONLY if present in the profile.
# Stored NORMALIZED (see _norm) so paren/slash variants match ("Kubernetes (AKS)").
_AI_MUST_HAVE_RAW = [
    "Docker", "Kubernetes (AKS)", "Terraform", "CI/CD", "Airflow", "Snowflake",
    "BigQuery", "PySpark/Spark", "Databricks", "Prompt Engineering",
    "Retrieval-Augmented Generation (RAG)", "Multi-Agent Orchestration",
    "Azure OpenAI", "MLOps/LLMOps", "OpenTelemetry", "LangGraph", "FastAPI",
]
# Categories to drop for AI/ML roles when they score low (off-theme).
_OFFROLE_CATEGORIES = {"Frontend"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


_AI_MUST_HAVE = {_norm(x) for x in _AI_MUST_HAVE_RAW}


def _is_ai_role(job: JobPosting) -> bool:
    t = _norm(f"{job.title} {' '.join(job.required_quals)}")
    return any(k in t for k in ("ai", "ml", "machine learning", "data scien",
                                "data engineer", "genai", "llm", "nlp", "agentic"))


def rank_skills(job: JobPosting, *, keyword_set: KeywordSet | None = None,
                max_items: int = 30, per_category_cap: int = 8) -> dict[str, list[str]]:
    p = prof.load_profile()
    profile_skills: dict[str, list[str]] = p.get("skills", {})
    ai_role = _is_ai_role(job)

    jd_text = _norm(" ".join([job.title, *job.required_quals, *job.preferred_quals,
                              *job.responsibilities]))
    jd_tokens = set(jd_text.split())
    kw_norm = {_norm(k.term): (k.weight if k.kind == "hard" else k.weight * 0.5)
               for k in (keyword_set.keywords if keyword_set else [])}

    def score(skill: str) -> float:
        n = _norm(skill)
        s = 0.0
        if n in kw_norm:                       # exact JD keyword match (weighted)
            s += 3.0 + kw_norm[n]
        toks = [t for t in n.split() if len(t) > 1]
        if toks and all(t in jd_tokens for t in toks):
            s += 2.0                            # full phrase appears in JD text
        elif any(t in jd_tokens for t in toks):
            s += 1.0                            # partial mention
        if ai_role and n in _AI_MUST_HAVE:
            s += 2.5                            # guarantee role-standard tools survive
        return s

    # score every grounded skill, keep category structure
    scored: dict[str, list[tuple[str, float]]] = {}
    for cat, items in profile_skills.items():
        if ai_role and cat in _OFFROLE_CATEGORIES:
            ranked = [(s, score(s)) for s in items]
            ranked = [(s, sc) for s, sc in ranked if sc >= 3.0]  # only if strongly JD-relevant
        else:
            ranked = [(s, score(s)) for s in items]
            ranked = [(s, sc) for s, sc in ranked
                      if sc > 0 or _norm(s) in _AI_MUST_HAVE]
        ranked.sort(key=lambda x: -x[1])
        if ranked:
            scored[cat] = ranked[:per_category_cap]

    # global cap: drop lowest-scoring items across categories, but never a must-have
    flat = [(cat, s, sc) for cat, lst in scored.items() for s, sc in lst]
    if len(flat) > max_items:
        keep = sorted(flat, key=lambda x: (_norm(x[1]) in _AI_MUST_HAVE, x[2]),
                      reverse=True)[:max_items]
        keepset = {(c, s) for c, s, _ in keep}
        scored = {cat: [(s, sc) for s, sc in lst if (cat, s) in keepset]
                  for cat, lst in scored.items()}
        scored = {c: v for c, v in scored.items() if v}

    # order categories by their best skill score; emit plain lists
    out_cats = sorted(scored, key=lambda c: -max(sc for _, sc in scored[c]))
    return {cat: [s for s, _ in scored[cat]] for cat in out_cats}
