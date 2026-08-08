"""Eval for Task 1.4 gap analysis (against the real canonical profile).

Cases (one LLM call):
  - "Python"                    -> existing (named skill)
  - "NL2SQL / natural language to SQL" -> supportedByResume (in a Granite bullet)
  - "AWS Lambda"                -> gap bridged by substitution (owns GCP Cloud Run)
  - "Rust programming language" -> true gap (no evidence, no bridge)

Run: `uv run python -m pocs.gap.eval`
"""
from __future__ import annotations

from evals.harness import run_eval
from pocs.gap import analyze_gaps

REQS = [
    "Python",
    "NL2SQL (natural language to SQL)",
    "AWS Lambda",
    "Rust programming language",
]


def build_cases():
    return [{"label": "profile-gap-classification", "input": REQS, "expect": None}]


def _find(report, needle):
    for it in report.items:
        if needle.lower() in it.requirement.lower():
            return it
    return None


def _run(reqs):
    return analyze_gaps(reqs, model="sonnet")


def _score(report, _):
    py = _find(report, "Python")
    nl = _find(report, "NL2SQL")
    lam = _find(report, "Lambda")
    rust = _find(report, "Rust")
    problems = []
    if not py or py.status != "existing":
        problems.append(f"Python not existing (got {py and py.status})")
    if not nl or nl.status not in ("existing", "supportedByResume"):
        problems.append(f"NL2SQL should be supported (got {nl and nl.status})")
    if not lam or not lam.substitution:
        problems.append(f"AWS Lambda should bridge to an owned tool (got sub={lam and lam.substitution!r})")
    if not rust or rust.status != "gap" or rust.substitution:
        problems.append(f"Rust should be a true gap (got {rust and rust.status}, sub={rust and rust.substitution!r})")
    if problems:
        return False, "; ".join(problems)
    return True, (f"Python={py.status}, NL2SQL={nl.status}, "
                  f"Lambda~>{lam.substitution}, Rust={rust.status}")


if __name__ == "__main__":
    run_eval("gap_analysis", build_cases(), _run, _score)
