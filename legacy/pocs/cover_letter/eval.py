"""Eval for Task 1.12 cover letter.

1 live case (Claude CLI, subscription -> $0 API): generate for the State Street
role and assert it is grounded, on-length, personalized, ASCII/anti-AI-tell.
2 zero-LLM unit cases: the grounding gate catches a fabricated metric; the lint
catches buzzwords + em-dashes.

Run: `uv run python -m pocs.cover_letter.eval`
"""
from __future__ import annotations

from evals.harness import run_eval
from pocs.ats.eval import _ss_job
from pocs.cover_letter import write_cover_letter
from pocs.cover_letter.writer import _lint
from pocs.fact_gate import ungrounded_metrics

_CL = None


def _letter():
    """Generate the State Street letter exactly ONCE (reused by print + eval)."""
    global _CL
    if _CL is None:
        _CL = write_cover_letter(_ss_job(), model="sonnet")
    return _CL


def build_cases():
    return [
        {"label": "state-street-letter (LLM)", "input": "gen", "expect": "gen"},
        {"label": "grounding-catches-fake-metric ($0)", "input": "ground", "expect": "ground"},
        {"label": "lint-catches-buzzwords-and-emdash ($0)", "input": "lint", "expect": "lint"},
    ]


def _run(kind):
    if kind == "gen":
        return _letter()
    if kind == "ground":
        return (ungrounded_metrics("We prevented $6 million in fraud last year."),   # grounded
                ungrounded_metrics("We prevented $500 million in fraud last year."))  # fabricated
    if kind == "lint":
        return _lint("I would leverage my robust, proven track record — with passion.")
    raise ValueError(kind)


def _score(out, kind):
    if kind == "gen":
        cl = out
        checks = {
            "grounded": cl.passed,
            "wordcount_ok": 170 <= cl.word_count <= 360,
            "names_company": "state street" in cl.text.lower(),
            "on_topic": any(k in cl.text.lower() for k in ("orchestration", "agent", "rag", "ai")),
            "ascii": all(ord(c) < 128 for c in cl.text),
            "paras_2_5": 2 <= len(cl.paragraphs) <= 5,
        }
        ok = all(checks.values())
        return ok, (f"words={cl.word_count} paras={len(cl.paragraphs)} passed={cl.passed} "
                    f"warnings={cl.warnings} checks={checks}")
    if kind == "ground":
        grounded, fabricated = out
        ok = grounded == [] and fabricated == ["$500 million"]
        return ok, f"grounded_empty={grounded} fabricated_flagged={fabricated}"
    if kind == "lint":
        ok = any("buzzword" in w.lower() for w in out) and any("dash" in w.lower() for w in out)
        return ok, str(out)
    return False, "unknown"


if __name__ == "__main__":
    cl = _letter()
    print("=" * 70)
    print(cl.text)
    print("=" * 70)
    print(f"words={cl.word_count} passed={cl.passed} warnings={cl.warnings}\n")
    run_eval("cover_letter", build_cases(), _run, _score)
