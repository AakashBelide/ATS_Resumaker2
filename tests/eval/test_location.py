"""Ported location eval (Task 1.L) as deterministic pytest cases. Zero-LLM, hermetic:
candidate fixed at Boston, MA; covers every strategy branch + blueprint §6 don'ts (never
a bare 'Remote', ZIP, or street address in the display)."""
from __future__ import annotations

import pytest

from resumaker.domain import JobPosting, WorkModel
from resumaker.stages.location import LocationPrefs, resolve_location

_BOSTON = "Boston, MA"


def _job(location="", work_model=WorkModel.unknown, remote_restriction=""):
    return JobPosting(title="AI Engineer", company="Acme", location=location,
                      work_model=work_model, remote_restriction=remote_restriction)


CASES = [
    ("quincy-is-boston-metro", _job("Quincy, Massachusetts", WorkModel.onsite),
     LocationPrefs(), "local", "Boston, MA", True),
    ("same-metro-cambridge", _job("Cambridge, MA", WorkModel.hybrid),
     LocationPrefs(), "local", "Boston, MA", None),
    ("remote-open", _job("Remote - US", WorkModel.remote),
     LocationPrefs(open_to_remote=True), "open_to_remote", "Boston, MA (Open to Remote)", None),
    ("remote-state-barred",
     _job("Remote", WorkModel.remote, remote_restriction="California residents only"),
     LocationPrefs(), "remote_ineligible", None, False),
    ("relocate-anywhere-bare-nyc", _job("New York, NY", WorkModel.onsite),
     LocationPrefs(relocate_anywhere=True), "relocating", "New York, NY", True),
    ("relocate-anywhere-suburb", _job("Bellevue, WA", WorkModel.onsite),
     LocationPrefs(relocate_anywhere=True), "relocating", "Seattle, WA", True),
    ("non-local-no-reloc", _job("Seattle, WA", WorkModel.onsite),
     LocationPrefs(relocate_anywhere=False), "non_local", "Boston, MA", False),
    ("unknown-jd-location", _job("", WorkModel.unknown),
     LocationPrefs(), "unknown_jd", "Boston, MA", True),
]


@pytest.mark.parametrize("label,job,prefs,strategy,display,passes",
                         CASES, ids=[c[0] for c in CASES])
def test_location_strategy(label, job, prefs, strategy, display, passes):
    plan = resolve_location(job, candidate_location=_BOSTON, prefs=prefs)
    assert plan.strategy == strategy
    if display is not None:
        assert plan.display == display
    if passes is not None:
        assert plan.passes_geo_filter == passes
    # blueprint §6 don'ts: never a bare 'Remote', ZIP, or empty display
    disp = plan.display.strip().lower()
    assert disp and disp != "remote" and not disp.isdigit()
