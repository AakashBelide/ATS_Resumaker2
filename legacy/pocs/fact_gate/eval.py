"""Eval for Task 1.9 fact-gate ($0, no LLM). Verifies it PASSES grounded content
and BLOCKS fabricated metrics / unknown employers / forbidden phrases.
Run: `uv run python -m pocs.fact_gate.eval`
"""
from __future__ import annotations

from core.schemas import ResumeContent
from evals.harness import run_eval
from pocs.fact_gate import verify_resume

GROUNDED = ResumeContent(
    headline="AI Engineer",
    summary="AI engineer with 3+ years building agentic systems.",
    experiences=[
        {"title": "Data Science and AI Engineer", "organization": "Bajaj Finserv",
         "dates": "Jul 2022 - Jan 2024",
         "bullets": ["Saved over **$1.19 million** with a graph deduplication engine "
                     "(**10B+** edges).",
                     "Cut deployment costs **30%** by migrating APIs to Kubernetes."]},
        {"title": "Data Science Intern", "organization": "Granite Telecommunications",
         "dates": "June 2025 - Dec 2025",
         "bullets": ["Improved data completeness **35%** across **20,000+** records."]},
    ],
    skills={"AI": ["LangGraph", "RAG"]})

FABRICATED = ResumeContent(
    headline="AI Engineer",
    summary="Delivered impact across the org.",
    experiences=[
        {"title": "Principal Engineer", "organization": "Globex Corporation",
         "dates": "2020 - 2024",
         "bullets": ["Generated **$500 million** in new revenue.",
                     "Built ML models with **99.9%** accuracy for a Fortune 500 client."]},
    ],
    skills={"AI": ["Rust"]})


def build_cases():
    return [
        {"label": "grounded-passes", "input": GROUNDED, "expect": {"passed": True}},
        {"label": "fabricated-blocked", "input": FABRICATED, "expect": {"passed": False}},
    ]


def _run(content):
    return verify_resume(content)


def _score(rep, expect):
    if rep.passed != expect["passed"]:
        return False, f"passed={rep.passed} (blockers={rep.blockers})"
    detail = "PASS clean" if rep.passed else f"blocked on: {rep.blockers}"
    return True, detail


if __name__ == "__main__":
    run_eval("fact_gate", build_cases(), _run, _score)
