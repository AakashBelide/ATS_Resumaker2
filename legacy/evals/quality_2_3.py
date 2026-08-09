"""Task 2.3 - end-to-end quality eval on real, current, related JDs.

Discovers live AI/ML/GenAI/DS/DE postings from public ATS feeds (Greenhouse/Lever/
Ashby), runs the full pipeline on each, and aggregates the quality metrics that
matter (blueprint 17): fact-gate pass %, ATS-verify pass %, ATS score, and the
primary success metric - RE-DRAFTS ~= 0 (a resume needs a re-draft only if a HARD
gate fails: fact-gate blocked, ATS-verify blocked, page overflow, or a run error).

    uv run python -m evals.quality_2_3 discover        # just list found jobs ($0)
    uv run python -m evals.quality_2_3 run [N]          # full eval on N jobs
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

from orchestrator import run_pipeline

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0"}
_SCRATCH = Path(__file__).resolve().parents[2] / "outputs" / "_quality_2_3"

# Related IC roles (owner's archetypes); skip clearly-senior/non-IC titles.
TITLE_RE = re.compile(
    r"\b(ai engineer|machine learning|ml engineer|gen ?ai|generative ai|llm|"
    r"data scientist|data engineer|applied scien|ai/ml|mlops|agentic|nlp)\b", re.I)
SKIP_RE = re.compile(r"\b(director|vp|vice president|head of|principal|staff|"
                     r"manager|intern|lead|president|chief)\b", re.I)

# Public ATS boards known to carry AI/ML roles (tolerant: missing boards are skipped).
GREENHOUSE = ["databricks", "anthropic", "gitlab", "benchling", "samsara",
              "discord", "coinbase", "dropbox", "pinterest", "robinhood",
              "sofi", "cloudflare", "airtable", "affirm"]
LEVER = ["voleon", "netflix", "plaid"]
ASHBY = ["openai", "ramp", "notion", "runway", "perplexity-ai"]


def _gh(token: str):
    r = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                  headers=UA, timeout=15, follow_redirects=True)
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        # Canonical boards.greenhouse.io URL so scrape() uses the JSON API (not Playwright).
        url = f"https://boards.greenhouse.io/{token}/jobs/{j.get('id')}"
        yield token, "greenhouse", j.get("title", ""), url


def _lever(site: str):
    r = httpx.get(f"https://api.lever.co/v0/postings/{site}?mode=json",
                  headers=UA, timeout=15, follow_redirects=True)
    r.raise_for_status()
    for j in r.json():
        yield site, "lever", j.get("text", ""), j.get("hostedUrl", "")


def _ashby(site: str):
    r = httpx.get(f"https://api.ashbyhq.com/posting-api/job-board/{site}",
                  headers=UA, timeout=15, follow_redirects=True)
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        url = j.get("jobUrl") or f"https://jobs.ashbyhq.com/{site}/{j.get('id','')}"
        yield site, "ashby", j.get("title", ""), url


def discover(n: int = 10, per_company: int = 1) -> list[dict]:
    found: list[dict] = []
    seen_co: dict[str, int] = {}
    sources = ([(_gh, t) for t in GREENHOUSE] + [(_lever, s) for s in LEVER]
               + [(_ashby, s) for s in ASHBY])
    for fn, key in sources:
        if len(found) >= n:
            break
        try:
            rows = list(fn(key))
        except Exception:  # noqa: BLE001 - board 404/renamed; skip
            continue
        for company, provider, title, url in rows:
            if not (title and url) or not TITLE_RE.search(title) or SKIP_RE.search(title):
                continue
            if seen_co.get(key, 0) >= per_company:
                continue
            found.append({"company": company, "provider": provider,
                          "title": title, "url": url})
            seen_co[key] = seen_co.get(key, 0) + 1
            if len(found) >= n:
                break
    return found


def _metrics(job_meta: dict, res) -> dict:
    r = res
    redraft = bool(r.error) or (r.resume is None) or \
        (r.fact_gate and not r.fact_gate.passed) or \
        (r.ats_verify and not r.ats_verify.passed) or \
        (r.resume and r.resume.page_count > 1)
    return {
        **job_meta,
        "error": r.error,
        "fit": r.fit.final_0_100 if r.fit else None,
        "apply": r.decision.recommend_apply if r.decision else None,
        "pages": r.resume.page_count if r.resume else None,
        "fact_gate": r.fact_gate.passed if r.fact_gate else None,
        "ats_verify": r.ats_verify.passed if r.ats_verify else None,
        "ats_verify_warnings": len(r.ats_verify.warnings) if r.ats_verify else None,
        "ats_overall": r.ats.overall_0_100 if r.ats else None,
        "ats_band": r.ats.band if r.ats else None,
        "cover_grounded": r.cover_letter.passed if r.cover_letter else None,
        "redraft_needed": redraft,
        "seconds": round(sum(r.timings.values()), 1) if r.timings else None,
    }


def run(n: int = 10) -> None:
    jobs = discover(n)
    print(f"Discovered {len(jobs)} related live jobs:\n")
    for i, j in enumerate(jobs):
        print(f"  {i+1:2}. [{j['provider']}] {j['company']:14} {j['title'][:52]}")
    print("\nRunning full pipeline on each (this takes a few minutes/job)...\n")

    results: list[dict] = []
    for i, j in enumerate(jobs):
        print(f"--- {i+1}/{len(jobs)}: {j['company']} / {j['title'][:50]} ---", flush=True)
        t0 = time.time()
        try:
            res = run_pipeline(j["url"], out_dir=str(_SCRATCH / f"{i:02d}"),
                               make_cover_letter=True)
            m = _metrics(j, res)
        except Exception as e:  # noqa: BLE001
            m = {**j, "error": f"harness: {type(e).__name__}: {e}", "redraft_needed": True}
        m["wall_s"] = round(time.time() - t0, 1)
        results.append(m)
        print(f"    fit={m.get('fit')} apply={m.get('apply')} pages={m.get('pages')} "
              f"fact_gate={m.get('fact_gate')} ats_verify={m.get('ats_verify')} "
              f"ats={m.get('ats_overall')} redraft={m.get('redraft_needed')} "
              f"({m['wall_s']}s)", flush=True)

    _summarize(results)
    _SCRATCH.mkdir(parents=True, exist_ok=True)
    (_SCRATCH / "quality_report.json").write_text(json.dumps(results, indent=1, default=str))
    print(f"\nSaved: {_SCRATCH / 'quality_report.json'}")


def _summarize(results: list[dict]) -> None:
    n = len(results)
    ok = [r for r in results if not r.get("error")]
    def pct(pred):
        vals = [r for r in ok if pred(r) is not None]
        return (100.0 * sum(bool(pred(r)) for r in vals) / len(vals)) if vals else 0.0
    ats = [r["ats_overall"] for r in ok if r.get("ats_overall") is not None]
    fits = [r["fit"] for r in ok if r.get("fit") is not None]
    redrafts = sum(1 for r in results if r.get("redraft_needed"))
    print("\n" + "=" * 68)
    print(f"QUALITY EVAL (2.3): {n} jobs, {len(ok)} ran without error")
    print(f"  fact-gate pass : {pct(lambda r: r.get('fact_gate')):.0f}%")
    print(f"  ATS-verify pass: {pct(lambda r: r.get('ats_verify')):.0f}%")
    print(f"  1-page         : {pct(lambda r: r.get('pages') == 1):.0f}%")
    print(f"  cover grounded : {pct(lambda r: r.get('cover_grounded')):.0f}%")
    print(f"  avg ATS score  : {sum(ats)/len(ats):.1f}" if ats else "  avg ATS score  : n/a")
    print(f"  avg fit        : {sum(fits)/len(fits):.1f}" if fits else "  avg fit        : n/a")
    print(f"  RE-DRAFTS needed: {redrafts}/{n}  (target ~= 0)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    if cmd == "discover":
        for j in discover(int(sys.argv[2]) if len(sys.argv) > 2 else 10):
            print(f"[{j['provider']}] {j['company']:14} {j['title'][:55]}  {j['url']}")
    elif cmd == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
