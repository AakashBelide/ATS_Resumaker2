"""Eval for Task 1.L - JD-aware location presentation. Zero-LLM ($0).

Candidate fixture: Boston, MA (F-1 CPT/OPT, nationwide-authorized). Cases cover
every strategy branch + the blueprint §6 don'ts (no bare 'Remote', no ZIP, no
street address ever leaks into the display).

Run: `uv run python -m pocs.location.eval`
"""
from __future__ import annotations

from core.schemas import JobPosting, WorkModel
from evals.harness import run_eval
from pocs.location import LocationPrefs, resolve_location

_BOSTON = "Boston, MA"


def _job(location="", work_model=WorkModel.unknown, remote_restriction=""):
    return JobPosting(title="AI Engineer", company="Acme",
                      location=location, work_model=work_model,
                      remote_restriction=remote_restriction)


def build_cases():
    return [
        # Real State Street case: Quincy MA is Boston-metro -> LOCAL, not a geo miss.
        {"label": "quincy-ma-is-boston-metro",
         "input": (_job("Quincy, Massachusetts", WorkModel.onsite),
                   LocationPrefs()),
         "expect": {"strategy": "local", "display": "Boston, MA", "passes": True}},
        # Same metro, onsite -> local.
        {"label": "same-metro-cambridge",
         "input": (_job("Cambridge, MA", WorkModel.hybrid), LocationPrefs()),
         "expect": {"strategy": "local", "display": "Boston, MA"}},
        # Remote, open, no restriction -> Open to Remote (never bare 'Remote').
        {"label": "remote-open",
         "input": (_job("Remote - US", WorkModel.remote), LocationPrefs(open_to_remote=True)),
         "expect": {"strategy": "open_to_remote", "display": "Boston, MA (Open to Remote)"}},
        # Remote restricted to CA -> ineligible (Boston candidate), keep real metro + warn.
        {"label": "remote-state-barred",
         "input": (_job("Remote", WorkModel.remote, remote_restriction="California residents only"),
                   LocationPrefs()),
         "expect": {"strategy": "remote_ineligible", "passes": False}},
        # Different metro, willing to relocate + listed -> committed relocation line.
        {"label": "relocating-to-nyc",
         "input": (_job("New York, NY", WorkModel.onsite),
                   LocationPrefs(willing_to_relocate=True,
                                 relocation_metros=["New York, NY"],
                                 relocation_timeframe="Q4 2026")),
         "expect": {"strategy": "relocating",
                    "display": "Relocating to New York, NY (Q4 2026)"}},
        # Suburb of a target metro also normalizes: Jersey City -> New York, NY.
        {"label": "relocating-suburb-normalizes",
         "input": (_job("Jersey City, NJ", WorkModel.onsite),
                   LocationPrefs(willing_to_relocate=True,
                                 relocation_metros=["New York, NY"])),
         "expect": {"strategy": "relocating", "display": "Relocating to New York, NY"}},
        # Different metro, NOT relocating -> keep real metro, fail geo, warn.
        {"label": "non-local-no-reloc",
         "input": (_job("Seattle, WA", WorkModel.onsite), LocationPrefs()),
         "expect": {"strategy": "non_local", "display": "Boston, MA", "passes": False}},
        # JD location unspecified -> present real metro, no false geo-fail.
        {"label": "unknown-jd-location",
         "input": (_job("", WorkModel.unknown), LocationPrefs()),
         "expect": {"strategy": "unknown_jd", "display": "Boston, MA", "passes": True}},
    ]


def _run(inp):
    job, prefs = inp
    return resolve_location(job, candidate_location=_BOSTON, prefs=prefs)


def _score(plan, expect):
    checks = []
    ok = True
    if "strategy" in expect:
        s = plan.strategy == expect["strategy"]
        ok &= s
        checks.append(f"strategy={plan.strategy}" + ("" if s else f" (want {expect['strategy']})"))
    if "display" in expect:
        d = plan.display == expect["display"]
        ok &= d
        checks.append(f"display={plan.display!r}" + ("" if d else f" (want {expect['display']!r})"))
    if "passes" in expect:
        pf = plan.passes_geo_filter == expect["passes"]
        ok &= pf
        checks.append(f"passes={plan.passes_geo_filter}")
    # blueprint §6 don'ts: display must never be a bare 'Remote', a ZIP, or a street address.
    disp = plan.display.strip().lower()
    if disp == "remote" or disp.isdigit():
        ok = False; checks.append("VIOLATION: bare Remote/ZIP in display")
    return ok, "  ".join(checks)


if __name__ == "__main__":
    run_eval("location", build_cases(), _run, _score)
