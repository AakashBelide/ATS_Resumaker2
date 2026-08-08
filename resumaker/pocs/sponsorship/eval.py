"""Eval for Task 1.5 sponsorship scorer.

Runs against REAL USCIS H-1B Employer Data Hub data (downloaded once to the
gitignored cache). No LLM -> $0.

Cases:
  1-4. Known high-volume H-1B sponsors (Amazon, Google, Cognizant, Infosys)
       must score `high`.
  5.   A made-up tiny employer must score `low` or `unknown`.
  6.   Normalization: "Google LLC" and "Google Inc" must resolve to the SAME
       USCIS record (same normalized_name), proving suffix-folding works.

Run: `uv run python -m pocs.sponsorship.eval`
"""
from __future__ import annotations

from evals.harness import run_eval
from pocs.sponsorship import get_index, score_company

_IDX = None


def _idx():
    global _IDX
    if _IDX is None:
        _IDX = get_index()
    return _IDX


def build_cases():
    return [
        {"label": "amazon-high", "input": "Amazon", "expect": {"likelihood": "high"}},
        {"label": "google-high", "input": "Google", "expect": {"likelihood": "high"}},
        {"label": "cognizant-high", "input": "Cognizant",
         "expect": {"likelihood": "high"}},
        {"label": "infosys-high", "input": "Infosys", "expect": {"likelihood": "high"}},
        {"label": "madeup-tiny", "input": "Zorblax Quijibo Widgets XYZ123",
         "expect": {"likelihood_in": ["low", "unknown"]}},
        {"label": "normalization-google-llc-vs-inc",
         "input": ("Google LLC", "Google Inc"),
         "expect": {"same_record": True}},
    ]


def _run(inp):
    if isinstance(inp, tuple):
        a, b = inp
        return (score_company(a, _idx()), score_company(b, _idx()))
    return score_company(inp, _idx())


def _score(out, expect):
    if "likelihood" in expect:
        ok = out.likelihood == expect["likelihood"]
        return ok, (f"likelihood={out.likelihood} count_3y={out.lca_count_3y:,} "
                    f"rate={out.approval_rate} norm={out.normalized_name!r}")
    if "likelihood_in" in expect:
        ok = out.likelihood in expect["likelihood_in"]
        return ok, f"likelihood={out.likelihood} (expected one of {expect['likelihood_in']})"
    if expect.get("same_record"):
        a, b = out
        ok = (a.normalized_name == b.normalized_name and a.normalized_name != ""
              and a.likelihood == b.likelihood)
        return ok, (f"'{a.company}'->{a.normalized_name!r} ({a.likelihood}) vs "
                    f"'{b.company}'->{b.normalized_name!r} ({b.likelihood})")
    return False, "unknown expectation"


if __name__ == "__main__":
    idx = _idx()
    print(f"USCIS index: FY{idx.fiscal_years}, "
          f"{len(idx.norm_keys):,} normalized employers")
    run_eval("sponsorship", build_cases(), _run, _score)
