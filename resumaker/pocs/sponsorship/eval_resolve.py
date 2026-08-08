"""Deterministic eval ($0, no LLM) for the sponsorship precedence rule
(resolve_sponsorship). Verifies that the JD's explicit stance OVERRIDES USCIS
company history, and that a silent JD falls back to history.

Run: `uv run python -m pocs.sponsorship.eval_resolve`
"""
from __future__ import annotations

from core.schemas import JobPosting, SponsorSignal
from evals.harness import run_eval
from pocs.sponsorship.resolve import resolve_sponsorship

HIGH = SponsorSignal(company="Acme", likelihood="high", lca_count_3y=5000,
                     most_recent_fy="2023", confidence="high")
UNKNOWN = SponsorSignal(company="Acme", likelihood="unknown")
LOWCONF = SponsorSignal(company="Acme", likelihood="high", lca_count_3y=20,
                        most_recent_fy="2023", confidence="low", needs_verification=True)


def build_cases():
    return [
        # JD explicitly excludes -> hard blocker EVEN with high company history
        {"label": "jd-no-overrides-high-history",
         "input": (JobPosting(company="Acme", sponsorship_stance="no_sponsorship"), HIGH),
         "expect": {"verdict": "not_eligible", "hard_blocker": True, "source": "jd_explicit"}},
        # JD explicitly offers -> eligible
        {"label": "jd-offers",
         "input": (JobPosting(company="Acme", sponsorship_stance="offers"), UNKNOWN),
         "expect": {"verdict": "eligible", "hard_blocker": False, "source": "jd_explicit"}},
        # JD silent + high history -> likely (from history)
        {"label": "silent-falls-back-to-history",
         "input": (JobPosting(company="Acme", sponsorship_stance="unclear"), HIGH),
         "expect": {"verdict": "likely", "hard_blocker": False, "source": "uscis_history"}},
        # JD silent + no history -> unknown
        {"label": "silent-no-history",
         "input": (JobPosting(company="Acme", sponsorship_stance="unclear"), UNKNOWN),
         "expect": {"verdict": "unknown", "hard_blocker": False, "source": "none"}},
        # JD silent + low-confidence history -> likely but needs_verification
        {"label": "silent-lowconf-history-flags-verify",
         "input": (JobPosting(company="Acme", sponsorship_stance="unclear"), LOWCONF),
         "expect": {"verdict": "likely", "needs_verification": True}},
    ]


def _run(inp):
    job, sig = inp
    return resolve_sponsorship(job, sig)


def _score(v, expect):
    for k, want in expect.items():
        got = getattr(v, k)
        if got != want:
            return False, f"{k}={got} != {want}"
    return True, f"verdict={v.verdict} hard_blocker={v.hard_blocker} source={v.source}"


if __name__ == "__main__":
    run_eval("sponsorship_resolve", build_cases(), _run, _score)
