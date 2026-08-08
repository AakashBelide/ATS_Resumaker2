"""Apply / no-apply decision (Task 1.7).

Deterministic combiner (no LLM -> consistent, explainable). Fuses three signals:
  - role fit (Task 1.6)
  - sponsorship verdict (Task 1.5 + JD stance, via resolve_sponsorship)
  - hard knockouts parsed from the JD (Task 1.2): years-of-experience, etc.

Hard blockers force no-apply regardless of fit. Otherwise the fit score drives the
recommendation. Human-in-the-loop: this advises; it never applies (blueprint §21).
"""
from __future__ import annotations

import re

from core import profile as prof
from core.schemas import ApplyDecision, FitScore, JobPosting
from pocs.sponsorship.resolve import SponsorshipVerdict

# Fit thresholds (0-100). Tunable; accuracy-first favors not wasting effort on
# weak fits (career-ops discourages low-fit applies).
_APPLY = 60.0       # >= -> recommend apply
_MARGINAL = 45.0    # >= -> marginal (apply with caution)


def _required_years(job: JobPosting) -> float | None:
    """Largest 'N+ years' requirement stated in the JD (knockouts + required quals)."""
    texts = [k.question for k in job.knockouts if k.kind == "years_experience"]
    texts += list(job.required_quals)
    best = None
    for t in texts:
        for m in re.finditer(r"(\d+)\s*\+?\s*years", t.lower()):
            y = float(m.group(1))
            best = y if best is None else max(best, y)
    return best


def decide_apply(job: JobPosting, fit: FitScore,
                 sponsorship: SponsorshipVerdict,
                 *, candidate_years: float | None = None,
                 needs_sponsorship: bool | None = None) -> ApplyDecision:
    cand_years = prof.candidate_years() if candidate_years is None else candidate_years
    needs_sp = prof.needs_sponsorship() if needs_sponsorship is None else needs_sponsorship

    blockers: list[str] = []
    reasons: list[str] = []

    # (1) Sponsorship hard blocker (only blocks if the candidate needs it).
    if sponsorship.hard_blocker and needs_sp:
        blockers.append("JD explicitly excludes visa sponsorship, which this "
                        "candidate requires: " + "; ".join(sponsorship.reasons))
    elif sponsorship.verdict == "unlikely" and needs_sp:
        reasons.append("Company shows little/no H-1B history and JD is silent on "
                       "sponsorship; sponsorship is uncertain.")
    elif needs_sp:
        reasons.append(f"Sponsorship outlook: {sponsorship.verdict} ({sponsorship.source}).")

    # (2) Years-of-experience knockout (allow a 1-year grace band).
    req_years = _required_years(job)
    if req_years is not None and cand_years + 1 < req_years:
        # treat a large gap as a hard blocker, a small one as a caution
        if req_years - cand_years >= 3:
            blockers.append(f"JD requires ~{req_years:.0f}+ years; candidate has "
                            f"~{cand_years:.0f} (gap {req_years - cand_years:.0f}y).")
        else:
            reasons.append(f"Slightly under the {req_years:.0f}-year bar "
                           f"(~{cand_years:.0f}y) - borderline.")

    # (3) Fit-driven recommendation (only if no hard blockers).
    reasons.append(f"Role-fit {fit.final_0_100:.0f}/100 ({fit.final_1_5}/5): {fit.rationale}")

    if blockers:
        return ApplyDecision(recommend_apply=False, confidence="high",
                             reasons=reasons, blockers=blockers)

    if fit.final_0_100 >= _APPLY:
        conf = "high" if fit.final_0_100 >= 75 else "medium"
        return ApplyDecision(recommend_apply=True, confidence=conf, reasons=reasons)
    if fit.final_0_100 >= _MARGINAL:
        reasons.append("Marginal fit - apply only if the role is a priority; expect "
                       "a tailored resume to work harder.")
        return ApplyDecision(recommend_apply=True, confidence="low", reasons=reasons)
    reasons.append(f"Fit below the {_MARGINAL:.0f} bar - not recommended.")
    return ApplyDecision(recommend_apply=False, confidence="medium", reasons=reasons)


if __name__ == "__main__":
    import sys
    from pocs.jd_structure import structure_jd
    from pocs.role_fit import score_fit
    from pocs.scrape_jd import scrape
    from pocs.sponsorship import sponsor_signal
    from pocs.sponsorship.resolve import resolve_sponsorship

    job = structure_jd(scrape(sys.argv[1]))
    fit = score_fit(job)
    sig = sponsor_signal(job.company) if job.company else None
    verdict = resolve_sponsorship(job, sig)
    d = decide_apply(job, fit, verdict)
    print(f"APPLY: {d.recommend_apply}  (confidence={d.confidence})")
    for b in d.blockers:
        print("  BLOCKER:", b)
    for r in d.reasons:
        print("  -", r)
