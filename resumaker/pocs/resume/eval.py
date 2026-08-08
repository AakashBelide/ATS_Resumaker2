"""Eval for Task 1.8 resume generation (deterministic render+trim path, $0 - no LLM).

Builds a resume from the profile, runs the ATS-safe render + one-page trim, and
asserts: .docx & PDF exist, fits the page budget, text round-trips cleanly (ATS
parse), and the fact-gate passes. The LLM tailoring quality is validated separately
(fact-gate runs on real tailored output in CI-style checks). Run:
`uv run python -m pocs.resume.eval`
"""
from __future__ import annotations

from pathlib import Path

from core import profile as prof
from core.schemas import ResumeContent
from evals.harness import run_eval
from pocs.fact_gate import verify_resume
from pocs.resume.generate import _fit_pages
from pocs.resume.render_pdf import extract_text

_OUT = Path(__file__).resolve().parents[3] / "outputs" / "_eval18"


def _content_from_profile() -> ResumeContent:
    p = prof.load_profile()
    return ResumeContent(
        headline="AI Engineer",
        summary=p["summary"],
        experiences=[{"title": e["title"], "organization": e["organization"],
                      "location": e.get("location", ""),
                      "dates": f"{e.get('start_date','')} - {e.get('end_date','')}",
                      "bullets": [b["text"] for b in e["bullets"]]}
                     for e in p["experience"]],
        projects=[{"title": pr["title"], "dates": pr.get("date", ""),
                   "bullets": [b["text"] for b in pr["bullets"]]} for pr in p["projects"]],
        skills=p["skills"])


def build_cases():
    return [{"label": "render-trim-factgate-onepage", "input": 1, "expect": None}]


def _run(target_pages):
    content = _content_from_profile()
    docx, pdf, pages = _fit_pages(content, _OUT, "eval18", target_pages)
    return {"content": content, "docx": docx, "pdf": pdf, "pages": pages}


def _score(out, _):
    problems = []
    if not Path(out["docx"]).exists():
        problems.append("docx missing")
    if not Path(out["pdf"]).exists():
        problems.append("pdf missing")
    if out["pages"] > 1:
        problems.append(f"{out['pages']} pages > 1")
    txt = extract_text(out["pdf"])
    for probe in ["Bajaj", "Granite", "Northeastern"]:
        if probe not in txt:
            problems.append(f"{probe!r} not in extracted text (ATS parse)")
    rep = verify_resume(out["content"])
    if not rep.passed:
        problems.append(f"fact-gate blocked: {rep.blockers}")
    if problems:
        return False, "; ".join(problems)
    return True, f"pages={out['pages']}, text_ok, fact-gate PASS ({len(txt)} chars)"


if __name__ == "__main__":
    run_eval("resume_generation", build_cases(), _run, _score)
