"""End-to-end parity/regression harness (LIVE - hits real scraping + LLM).

Skipped by default; run explicitly:
    uv run pytest -m live tests/eval/test_pipeline_live.py

Asserts the full pipeline still produces a grounded, ATS-safe resume on a real JD:
no fatal error, 1-page, fact-gate PASS, ATS-verify PASS, a cover letter, and a run
row indexed in SQLite. This is the repeatable form of the R4 parity gate.
"""
from __future__ import annotations

import pytest

from resumaker.pipeline import run_pipeline


@pytest.mark.live
def test_full_pipeline_on_live_greenhouse_jd():
    from resumaker.providers.sources import get_source
    posts = get_source("greenhouse").list_postings("databricks")
    jd = next(p for p in posts if any(k in p.title for k in
              ("AI Engineer", "Machine Learning", "ML Engineer", "Applied AI")))

    res = run_pipeline(jd.url, make_cover_letter=True)

    assert not res.error, res.error
    assert res.job and res.resume and res.fact_gate and res.ats_verify
    assert res.resume.page_count == 1
    assert res.fact_gate.passed, res.fact_gate.blockers
    assert res.ats_verify.passed, res.ats_verify.warnings
    assert res.ats and res.ats.overall_0_100 > 0
    assert res.cover_letter and res.cover_letter.word_count > 100

    # run indexed in SQLite
    from resumaker.persistence import db
    assert any(r.out_dir == res.out_dir for r in db.list_runs(limit=10))
