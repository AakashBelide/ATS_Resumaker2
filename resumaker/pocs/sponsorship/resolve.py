"""Resolve a final, role-level sponsorship verdict by combining two signals with
the right precedence:

  1. THE JD ITSELF (authoritative, role-specific, current) -- `sponsorship_stance`
     parsed in Task 1.2. If the posting explicitly says no/offers sponsorship, that
     is decisive for THIS role and overrides company history.
  2. USCIS historical company signal (Task 1.5) -- only a *prior*, used when the JD
     is silent, and even then subject to the name-match confidence caveats.

This is what turns "does the company sponsor" into "is THIS role sponsorable".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.schemas import JobPosting, SponsorSignal


@dataclass
class SponsorshipVerdict:
    verdict: str                       # eligible | not_eligible | likely | unlikely | unknown
    hard_blocker: bool = False         # True only when the JD explicitly excludes sponsorship
    source: str = ""                   # "jd_explicit" | "uscis_history" | "none"
    needs_verification: bool = False
    reasons: list[str] = field(default_factory=list)


def resolve_sponsorship(job: JobPosting,
                        signal: SponsorSignal | None) -> SponsorshipVerdict:
    reasons: list[str] = []

    # (1) JD-explicit stance wins.
    stance = job.sponsorship_stance
    note = (job.work_auth_note or "").strip()
    if stance == "no_sponsorship":
        return SponsorshipVerdict(
            verdict="not_eligible", hard_blocker=True, source="jd_explicit",
            reasons=[f"JD explicitly excludes sponsorship"
                     + (f': \"{note}\"' if note else ".")])
    if stance == "offers":
        return SponsorshipVerdict(
            verdict="eligible", source="jd_explicit",
            reasons=[f"JD explicitly offers/allows sponsorship"
                     + (f': \"{note}\"' if note else ".")])
    if stance == "case_by_case":
        reasons.append(f"JD indicates case-by-case sponsorship"
                       + (f': \"{note}\"' if note else "."))
        # fall through to blend with history as supporting context

    # (2) JD silent (or case-by-case) -> fall back to USCIS company history as a prior.
    if signal is None or signal.likelihood == "unknown":
        reasons.append("JD does not state a sponsorship policy; no reliable USCIS "
                       "H-1B history matched for the company (absence != never sponsors).")
        v = "unknown" if stance != "case_by_case" else "unknown"
        return SponsorshipVerdict(verdict=v, source="none", reasons=reasons)

    reasons.append(
        f"JD silent on sponsorship; USCIS H-1B history for the company is "
        f"'{signal.likelihood}' ({signal.lca_count_3y:,} approvals, "
        f"most recent FY{signal.most_recent_fy}).")
    if signal.needs_verification:
        reasons.append("NOTE: company name matched with LOW confidence -- verify the "
                       "USCIS record is the same company.")

    mapping = {"high": "likely", "medium": "likely", "low": "unlikely"}
    return SponsorshipVerdict(
        verdict=mapping.get(signal.likelihood, "unknown"),
        source="uscis_history",
        needs_verification=signal.needs_verification,
        reasons=reasons)


if __name__ == "__main__":
    import sys
    from pocs.jd_structure import structure_jd
    from pocs.scrape_jd import scrape
    from pocs.sponsorship import sponsor_signal

    job = structure_jd(scrape(sys.argv[1]))
    sig = sponsor_signal(job.company) if job.company else None
    v = resolve_sponsorship(job, sig)
    print(f"company={job.company!r} jd_stance={job.sponsorship_stance} "
          f"work_auth_note={job.work_auth_note!r}")
    print(f"VERDICT: {v.verdict}  (hard_blocker={v.hard_blocker}, source={v.source}, "
          f"verify={v.needs_verification})")
    for r in v.reasons:
        print("  -", r)
