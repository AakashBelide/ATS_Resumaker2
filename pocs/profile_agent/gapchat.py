"""Flow 3 - match-time gap clarification (the keystone: talk -> re-match -> generate).

Seeds talking points from a completed match's report.json (its `gap` items and the
`supportedByResume`/have-but-unlisted signals), lets the user assert real evidence for genuine gaps
(never fabricating), then triggers a re-match against the enriched profile and, on confirmation,
resume generation. The score can only rise because real evidence flips gap items to
existing/supportedByResume in `analyze_gaps` -> `score_fit`; an unbacked assertion silently
downgrades back to `gap`, so a lie can't inflate the score.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resumaker.domain import JobPosting, KeywordSet
from resumaker.persistence import profile as profile_store
from resumaker.persistence.artifacts import get_artifact_store
from resumaker.pipeline import run_pipeline
from resumaker.providers.llm import get_provider

from . import agent, store
from .prompts import GAPCHAT_PROBE, GUARDRAIL

_SYSTEM = ("You help a candidate honestly clarify gaps between a job and their profile before a "
           "resume is generated. You focus on genuine gaps and never propose adding something the "
           "user cannot back with their own words.")


def _load_report(run_id: str) -> dict:
    raw = get_artifact_store().open(run_id, "report.json")
    if not raw:
        raise FileNotFoundError(f"no report.json for run {run_id!r} (run a match first)")
    return json.loads(raw)


def needs_clarification(report: dict) -> bool:
    """True if the report has any true gap or any supportedByResume (have-but-unlisted) item - the
    condition that makes the Generate button intercept with the nudge dialog."""
    items = (report.get("gap") or {}).get("items", [])
    return any(it.get("status") in ("gap", "supportedByResume") for it in items)


def _seed_lines(report: dict) -> tuple[list[str], list[str]]:
    items = (report.get("gap") or {}).get("items", [])
    gaps = [f"- {it['requirement']}" for it in items if it.get("status") == "gap"]
    unlisted = [f"- {it['requirement']}" for it in items if it.get("status") == "supportedByResume"]
    return gaps, unlisted


def start(report_run_id: str) -> store.RunState:
    """Open a gap-clarification chat seeded from a completed match's report.json."""
    report = _load_report(report_run_id)
    gaps, unlisted = _seed_lines(report)
    old_fit = float((report.get("fit") or {}).get("final_0_100", 0.0))
    st = store.new_run("gapchat", report_run_id=report_run_id, gap_lines=gaps,
                       unlisted_lines=unlisted, old_fit=old_fit)
    st.state = "needs_input"
    st.add_event("seed", "ok", f"{len(gaps)} gap(s), {len(unlisted)} have-but-unlisted; fit={old_fit:.0f}")
    store.save(st)
    return st


def _build_prompt(st: store.RunState, user_text: str) -> tuple[str, str]:
    prompt = GAPCHAT_PROBE.format(
        guardrail=GUARDRAIL,
        gap_lines="\n".join(st.meta.get("gap_lines", [])) or "(none)",
        unlisted_lines="\n".join(st.meta.get("unlisted_lines", [])) or "(none)",
        profile_text=profile_store.profile_text()[:12000],
        user_message=user_text)
    return _SYSTEM, prompt


def _regenerate(st: store.RunState) -> str:
    """Re-match against the enriched profile, then generate the resume. Called by /generate."""
    run_id = st.meta["report_run_id"]
    report = _load_report(run_id)
    job = JobPosting(**report["job"])
    keyword_set = KeywordSet(**report["keyword_set"]) if report.get("keyword_set") else None

    st.add_event("rematch", "start", "re-classifying gaps against the enriched profile")
    # gap=None forces analyze_gaps to re-run against the now-enriched profile
    rematch = run_pipeline(job=job, keyword_set=keyword_set, gap=None, run_id=run_id, match_only=True)
    new_fit = float(rematch.fit.final_0_100)
    old_fit = float(st.meta.get("old_fit", 0.0))
    st.add_event("rematch", "done", f"fit {old_fit:.0f} -> {new_fit:.0f}")

    st.add_event("generate", "start", "generating tailored resume + fact gate")
    gen = run_pipeline(job=job, keyword_set=keyword_set, gap=rematch.gap, run_id=run_id,
                       match_only=False, gate=True)
    gate = getattr(gen, "fact_gate", None)
    gate_ok = getattr(gate, "passed", None)
    st.meta["new_fit"] = new_fit
    st.add_event("generate", "done", f"fact_gate={'pass' if gate_ok else gate_ok}")
    return (f"Re-matched: fit {old_fit:.0f} -> {new_fit:.0f}. "
            f"Resume generated in run {run_id} (fact gate: {'passed' if gate_ok else gate_ok}).")


def say(st: store.RunState, message: str, *, llm: Any = None, profile_path: Path | None = None) -> str:
    llm = llm or get_provider("claude", model="sonnet")
    return agent.run_turn(st, message, build_prompt=_build_prompt, llm=llm,
                          on_generate=_regenerate, profile_path=profile_path)
