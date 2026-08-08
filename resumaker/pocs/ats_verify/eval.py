"""Eval for Task 1.10 ATS-parse verification. Zero-LLM ($0).

Good case = the saved State Street resume (content + rendered PDF) -> must PASS.
Bad cases exercise each blocker: non-ASCII, a likely typo, a fabricated employer,
inflated tenure, and (warning) a headline that omits the JD title.

Run: `uv run python -m pocs.ats_verify.eval`
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from core.schemas import JobPosting, ResumeContent, WorkModel
from evals.harness import run_eval
from pocs.ats_verify import verify_ats

_DIR = Path(__file__).resolve().parents[3] / "outputs" / "state-street-ai-orchestration-engineer"
_CONTENT = _DIR / "content.json"
_PDF = _DIR / "state-street-ai-orchestration-engineer.pdf"


def _job(title="AI Orchestration Engineer"):
    return JobPosting(title=title, company="State Street",
                      location="Quincy, Massachusetts", work_model=WorkModel.hybrid)


def _content() -> ResumeContent:
    return ResumeContent(**json.loads(_CONTENT.read_text()))


def _mutate(fn):
    c = _content()
    fn(c)
    return c


def build_cases():
    return [
        {"label": "good-resume-with-pdf-passes", "input": ("good", None), "expect": "pass"},
        {"label": "non-ascii-blocks", "input": ("mut", "ascii"), "expect": "blk:Non-ASCII"},
        {"label": "typo-blocks", "input": ("mut", "typo"), "expect": "blk:misspell"},
        {"label": "fabricated-employer-blocks", "input": ("mut", "fakeorg"),
         "expect": "blk:not in the profile"},
        {"label": "inflated-tenure-blocks", "input": ("mut", "tenure"),
         "expect": "blk:inflated tenure"},
        {"label": "headline-missing-jd-title-warns", "input": ("headline", None),
         "expect": "warn:does not contain the JD title"},
    ]


def _apply(kind):
    if kind == "ascii":
        return _mutate(lambda c: c.experiences[0]["bullets"].__setitem__(
            0, "Built a graph engine — saved money."))       # em-dash
    if kind == "typo":
        return _mutate(lambda c: c.experiences[0]["bullets"].__setitem__(
            0, "Managd end-to-end deployment of production services."))  # 'Managd'
    if kind == "fakeorg":
        return _mutate(lambda c: c.experiences.insert(
            0, {"organization": "Nonexistent Corp", "title": "Engineer",
                "dates": "Jan 2019 - Dec 2020", "bullets": ["Did stuff here."]}))
    if kind == "tenure":
        def infl(c):
            for e in c.experiences:
                if "bajaj" in e["organization"].lower():
                    e["dates"] = "Jan 2018 - Aug 2024"   # profile starts 2022
        return _mutate(infl)
    raise ValueError(kind)


def _run(inp):
    mode, arg = inp
    if mode == "good":
        return verify_ats(_job(), _content(), pdf_path=str(_PDF) if _PDF.exists() else None)
    if mode == "headline":
        return verify_ats(_job("Principal Robotics Engineer"), _content())
    return verify_ats(_job(), _apply(arg))


def _score(rep, expect):
    if expect == "pass":
        return rep.passed, (f"passed={rep.passed} blockers={rep.blockers} "
                            f"warnings={len(rep.warnings)} checks={list(rep.checks)}")
    tag, needle = expect.split(":", 1)
    pool = rep.blockers if tag == "blk" else rep.warnings
    hit = any(needle.lower() in x.lower() for x in pool)
    if tag == "blk":
        hit = hit and not rep.passed
    return hit, f"passed={rep.passed} looking_for={needle!r} in {tag}: {pool[:3]}"


if __name__ == "__main__":
    run_eval("ats_verify", build_cases(), _run, _score)
