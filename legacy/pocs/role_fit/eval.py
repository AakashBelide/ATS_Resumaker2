"""Eval for Task 1.6 role-fit scoring (against the real profile).

Verifies calibration/discrimination: a well-matched mid-level AI role scores high,
a staff-level frontend role (seniority + domain mismatch) scores low, and the two
are clearly separated. Run: `uv run python -m pocs.role_fit.eval`
"""
from __future__ import annotations

from core.schemas import JobPosting, WorkModel
from evals.harness import run_eval
from pocs.role_fit import score_fit

GOOD = JobPosting(
    title="AI Engineer", company="Acme AI", seniority="mid",
    required_quals=["3+ years Python", "LangGraph or agent frameworks",
                    "RAG pipelines", "AWS or GCP", "FastAPI"],
    preferred_quals=["Neo4j", "vector databases"],
    work_model=WorkModel.hybrid, location="Boston, MA")

POOR = JobPosting(
    title="Staff Frontend Engineer", company="PixelCo", seniority="staff",
    required_quals=["10+ years frontend", "Expert React and CSS",
                    "Design systems leadership", "Accessibility (WCAG)",
                    "Team leadership of 8+ engineers"],
    preferred_quals=["Figma"], work_model=WorkModel.onsite,
    location="San Francisco, CA")


def build_cases():
    return [
        {"label": "good-fit-ai-mid", "input": GOOD, "expect": {"min": 60}},
        {"label": "poor-fit-staff-frontend", "input": POOR, "expect": {"max": 40}},
    ]


def _run(job):
    return score_fit(job)


def _score(fs, expect):
    if "min" in expect and fs.final_0_100 < expect["min"]:
        return False, f"final={fs.final_0_100} < {expect['min']}"
    if "max" in expect and fs.final_0_100 > expect["max"]:
        return False, f"final={fs.final_0_100} > {expect['max']}"
    return True, f"final={fs.final_0_100}/100 ({fs.final_1_5}/5) det={fs.deterministic_0_100}"


if __name__ == "__main__":
    run_eval("role_fit", build_cases(), _run, _score)
