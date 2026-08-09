"""Deterministic eval ($0, no LLM) for Task 1.7 apply/no-apply.

Verifies: hard blockers (sponsorship exclusion, big experience gap) force no-apply
regardless of fit; otherwise fit drives the call. Run: `uv run python -m pocs.apply_decision.eval`
"""
from __future__ import annotations

from core.schemas import ApplyDecision, FitScore, JobPosting, Knockout
from evals.harness import run_eval
from pocs.apply_decision import decide_apply
from pocs.sponsorship.resolve import SponsorshipVerdict

FIT_GOOD = FitScore(final_0_100=81, final_1_5=4.0, rationale="strong match")
FIT_MARGINAL = FitScore(final_0_100=50, final_1_5=2.5, rationale="partial match")
FIT_LOW = FitScore(final_0_100=30, final_1_5=1.5, rationale="weak match")

SP_OK = SponsorshipVerdict(verdict="likely", source="uscis_history")
SP_BLOCK = SponsorshipVerdict(verdict="not_eligible", hard_blocker=True,
                              source="jd_explicit", reasons=["JD excludes sponsorship"])

JOB = JobPosting(title="AI Engineer", company="Acme")
JOB_10YR = JobPosting(title="Staff Engineer", company="Acme",
                      knockouts=[Knockout(question="10+ years of experience required",
                                          kind="years_experience")])


def build_cases():
    # candidate: 3 years, needs sponsorship (matches real profile defaults)
    return [
        {"label": "good-fit-eligible-APPLY",
         "input": (JOB, FIT_GOOD, SP_OK, 3.0, True),
         "expect": {"recommend_apply": True}},
        {"label": "good-fit-but-sponsorship-blocked",
         "input": (JOB, FIT_GOOD, SP_BLOCK, 3.0, True),
         "expect": {"recommend_apply": False, "has_blocker": True}},
        {"label": "sponsorship-block-ignored-if-not-needed",
         "input": (JOB, FIT_GOOD, SP_BLOCK, 3.0, False),
         "expect": {"recommend_apply": True}},
        {"label": "good-fit-but-10yr-knockout",
         "input": (JOB_10YR, FIT_GOOD, SP_OK, 3.0, True),
         "expect": {"recommend_apply": False, "has_blocker": True}},
        {"label": "low-fit-no-apply",
         "input": (JOB, FIT_LOW, SP_OK, 3.0, True),
         "expect": {"recommend_apply": False, "has_blocker": False}},
        {"label": "marginal-fit-apply-low-conf",
         "input": (JOB, FIT_MARGINAL, SP_OK, 3.0, True),
         "expect": {"recommend_apply": True, "confidence": "low"}},
    ]


def _run(inp):
    job, fit, sp, yrs, needs = inp
    return decide_apply(job, fit, sp, candidate_years=yrs, needs_sponsorship=needs)


def _score(d: ApplyDecision, expect):
    if d.recommend_apply != expect["recommend_apply"]:
        return False, f"recommend_apply={d.recommend_apply} != {expect['recommend_apply']}"
    if "has_blocker" in expect and bool(d.blockers) != expect["has_blocker"]:
        return False, f"blockers={d.blockers}"
    if "confidence" in expect and d.confidence != expect["confidence"]:
        return False, f"confidence={d.confidence} != {expect['confidence']}"
    return True, f"apply={d.recommend_apply} conf={d.confidence} blockers={len(d.blockers)}"


if __name__ == "__main__":
    run_eval("apply_decision", build_cases(), _run, _score)
