"""Eval for Phase 3 ATS + recruiter simulation. Zero-LLM ($0).

Uses the real generated State Street resume (extracted PDF text) as OUR candidate,
against the decoy pool. Asserts: (1) it parses into clean fields (high
completeness), (2) it surfaces for the recruiter Boolean must-haves, (3) it ranks
#1 above every decoy for the JD query.

Run: `uv run python -m pocs.ats_sim.eval`
"""
from __future__ import annotations

from pathlib import Path

from evals.harness import run_eval
from pocs.ats_sim import boolean_surface, parse_resume, rank_pool
from pocs.ats_sim.decoys import DECOYS

_DIR = (Path(__file__).resolve().parents[3] / "outputs" /
        "state-street-ai-orchestration-engineer")
_RESUME_PDF = _DIR / "state-street-ai-orchestration-engineer.pdf"
_RESUME_TXT = _DIR / "resume_extracted_text.txt"

# Recruiter's must-have Boolean terms + the fuller JD query for ranking.
MUST_HAVE = ["multi-agent orchestration", "RAG", "LangGraph", "MLOps", "observability", "agentic"]
JD_QUERY = MUST_HAVE + ["LLM", "Python", "SQL", "vector search", "Kubernetes", "Airflow",
                        "prompt engineering", "cloud", "agents", "deployment"]


def _our_text() -> str:
    # prefer extracting the CURRENT pdf (canonical); fall back to the saved text
    if _RESUME_PDF.exists():
        from pocs.resume.render_pdf import extract_text
        return extract_text(str(_RESUME_PDF))
    return _RESUME_TXT.read_text() if _RESUME_TXT.exists() else ""


def build_cases():
    return [
        {"label": "parse-fidelity-high", "input": "parse", "expect": "parse"},
        {"label": "surfaces-in-boolean-search", "input": "surface", "expect": "surface"},
        {"label": "ranks-1st-above-decoys", "input": "rank", "expect": "rank"},
    ]


def _run(kind):
    text = _our_text()
    if kind == "parse":
        return parse_resume(text)
    if kind == "surface":
        return boolean_surface(text, MUST_HAVE)
    if kind == "rank":
        pool = [("OURS", text)] + list(DECOYS)
        return rank_pool(JD_QUERY, pool)
    raise ValueError(kind)


def _score(out, kind):
    if kind == "parse":
        c = out
        ok = bool(c.completeness >= 85 and c.email and c.location
                  and len(c.sections) >= 4 and len(c.experience) >= 2 and c.skills)
        return ok, (f"completeness={c.completeness}% name={c.name!r} email={bool(c.email)} "
                    f"loc={c.location!r} sections={c.sections} "
                    f"exp={len(c.experience)} skills={len(c.skills)} missing={c.missing}")
    if kind == "surface":
        surfaces, present, absent = out
        return surfaces and len(present) >= 5, f"surfaces={surfaces} present={present} absent={absent}"
    if kind == "rank":
        rows = out
        ours = next(r for r in rows if r["label"] == "OURS")
        top = rows[0]
        margin = round(top["score"] - rows[1]["score"], 2) if len(rows) > 1 else 0
        ok = ours["rank"] == 1
        detail = " > ".join(f"{r['label']}({r['score']})" for r in rows[:4])
        return ok, f"our_rank={ours['rank']} margin_over_2nd={margin} | {detail}"
    return False, "unknown"


if __name__ == "__main__":
    c = parse_resume(_our_text())
    print("PARSE CARD:")
    for k in ("name", "email", "phone", "location", "links", "sections", "skills"):
        print(f"  {k}: {getattr(c, k)}")
    print(f"  experience: {[e['organization'] for e in c.experience]}")
    print(f"  completeness: {c.completeness}%  missing: {c.missing}\n")
    print("RECRUITER RANKING (JD query vs decoys):")
    for r in rank_pool(JD_QUERY, [("OURS", _our_text())] + list(DECOYS)):
        print(f"  #{r['rank']}  {r['score']:6.2f}  {r['label']}")
    print()
    run_eval("ats_sim", build_cases(), _run, _score)
