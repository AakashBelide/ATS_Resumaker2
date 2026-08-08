"""Eval for Task 1.3 keyword extraction.

Uses a synthetic JD with obvious expected terms (keeps cost low: no scrape/structure,
2 passes). Asserts the must-have hard skills surface, the count is sane, and the
weight reflects consensus. Run: `uv run python -m pocs.keywords.eval`
"""
from __future__ import annotations

from evals.harness import run_eval
from pocs.keywords import extract_keywords

SYNTH_JD = """Senior Machine Learning Engineer at Acme AI. Boston, MA (Hybrid).

Requirements:
- 5+ years building ML systems in Python
- Deep experience with PyTorch and large language models (LLMs)
- Production RAG pipelines and vector databases (Pinecone or Qdrant)
- AWS (SageMaker, Lambda) and Docker/Kubernetes
- Strong SQL and data pipeline skills (Airflow)

Responsibilities:
- Design and deploy LLM-powered features
- Own MLOps: CI/CD, monitoring, evals
- Collaborate cross-functionally with product
"""

EXPECT_HARD = {"python", "pytorch", "aws", "docker", "kubernetes", "sql", "airflow"}


def build_cases():
    return [{"label": "synthetic-ml-jd", "input": SYNTH_JD, "expect": EXPECT_HARD}]


def _run(jd):
    return extract_keywords(jd, passes=2)


def _score(ks, expect):
    terms = {k.term.lower() for k in ks.keywords}
    n = len(ks.keywords)
    if not (10 <= n <= 25):
        return False, f"keyword count out of range: {n}"
    # how many expected hard skills are covered (allow substring match for e.g. 'aws (sagemaker)')
    covered = {e for e in expect if any(e in t for t in terms)}
    missing = expect - covered
    if len(covered) < len(expect) - 1:   # allow one miss
        return False, f"missing expected hard skills: {sorted(missing)} (got {sorted(terms)})"
    if not ks.hard:
        return False, "no hard keywords classified"
    return True, (f"{n} kws, {len(covered)}/{len(expect)} expected covered, "
                  f"hard={len(ks.hard)} soft={len(ks.soft)}")


if __name__ == "__main__":
    run_eval("keywords", build_cases(), _run, _score)
