"""Eval for Task 1.11 - ATS scorer + semantic coverage + skills-ranker.

Uses the saved State Street content.json (real generated resume) as the good
case and a deliberately weak resume as the contrast. Lexical semantic method =>
deterministic + $0. Run: `uv run python -m pocs.ats.eval`
"""
from __future__ import annotations

import json
from pathlib import Path

from core.schemas import JobPosting, KeywordSet, ResumeContent, WeightedKeyword, WorkModel
from evals.harness import run_eval
from pocs.ats import rank_skills, score_ats

_SS = Path(__file__).resolve().parents[3] / "outputs" / \
    "state-street-ai-orchestration-engineer" / "content.json"


def _ss_job() -> JobPosting:
    return JobPosting(
        title="AI Orchestration Engineer", company="State Street",
        location="Quincy, Massachusetts", work_model=WorkModel.hybrid,
        required_quals=["Build multi-agent orchestration and agentic workflows",
                        "Design and deploy enterprise RAG systems",
                        "Production MLOps and observability",
                        "Large-scale data pipelines with Python and SQL"],
        responsibilities=["Orchestrate LLM agents in production",
                          "Instrument observability for AI systems",
                          "Deploy and monitor AI services on cloud"])


def _ss_keywords() -> KeywordSet:
    hard = ["multi-agent orchestration", "RAG", "MLOps", "observability", "LangGraph",
            "Python", "SQL", "Kubernetes", "Docker", "agentic", "vector search", "cloud"]
    soft = ["collaboration", "communication"]
    kws = [WeightedKeyword(term=t, weight=2.0, kind="hard") for t in hard] + \
          [WeightedKeyword(term=t, weight=1.0, kind="soft") for t in soft]
    return KeywordSet(keywords=kws, standardized=hard + soft)


def _good_content() -> ResumeContent:
    return ResumeContent(**json.loads(_SS.read_text()))


def _weak_content() -> ResumeContent:
    return ResumeContent(
        headline="Engineer", summary="Worked on various software projects.",
        experiences=[{"organization": "Acme", "title": "Engineer", "dates": "2022 - 2024",
                      "bullets": ["Did backend work.", "Helped the team.",
                                  "Wrote some code."]}],
        skills={"Skills": ["Java", "HTML"]})


def build_cases():
    return [
        {"label": "good-resume-scores-well", "input": "good",
         "expect": {"band_in": ["good", "fair"], "kw_min": 55, "struct_min": 90}},
        {"label": "weak-resume-scores-low", "input": "weak",
         "expect": {"band_in": ["weak"], "kw_max": 40}},
        {"label": "semantic-coverage-good>weak", "input": "compare",
         "expect": {"good_gt_weak": True}},
        {"label": "skills-ranker-keeps-infra-and-drops-frontend", "input": "skills",
         "expect": {"has": ["Docker", "Kubernetes (AKS)", "Terraform", "Airflow",
                            "Snowflake", "BigQuery"], "not_cat": "Frontend"}},
    ]


def _run(inp):
    job, ks = _ss_job(), _ss_keywords()
    if inp == "good":
        return score_ats(job, _good_content(), keyword_set=ks)
    if inp == "weak":
        return score_ats(job, _weak_content(), keyword_set=ks)
    if inp == "compare":
        return (score_ats(job, _good_content(), keyword_set=ks),
                score_ats(job, _weak_content(), keyword_set=ks))
    if inp == "skills":
        return rank_skills(job, keyword_set=ks)
    raise ValueError(inp)


def _score(out, expect):
    if "band_in" in expect and not isinstance(out, tuple) and hasattr(out, "band"):
        ok = out.band in expect["band_in"]
        if "kw_min" in expect:
            ok &= out.keyword_coverage >= expect["kw_min"]
        if "kw_max" in expect:
            ok &= out.keyword_coverage <= expect["kw_max"]
        if "struct_min" in expect:
            ok &= out.structure >= expect["struct_min"]
        return ok, (f"overall={out.overall_0_100} band={out.band} kw={out.keyword_coverage} "
                    f"quant={out.quantification} struct={out.structure} "
                    f"sem={out.semantic_coverage}% missing={out.missing_keywords[:4]} "
                    f"weak={out.weak_requirements[:2]}")
    if expect.get("good_gt_weak"):
        good, weak = out
        ok = good.semantic_coverage > weak.semantic_coverage
        return ok, f"good_sem={good.semantic_coverage}% > weak_sem={weak.semantic_coverage}%"
    if "has" in expect:
        flat = {s for items in out.values() for s in items}
        missing = [s for s in expect["has"] if s not in flat]
        cat_ok = expect["not_cat"] not in out
        ok = not missing and cat_ok
        return ok, (f"{sum(len(v) for v in out.values())} skills in {len(out)} cats; "
                    f"missing={missing or 'none'}; {expect['not_cat']}_dropped={cat_ok}")
    return False, "unknown"


if __name__ == "__main__":
    run_eval("ats", build_cases(), _run, _score)
