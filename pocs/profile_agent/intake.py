"""Flow 1 - onboarding intake: resume (+ optional LinkedIn PDF) -> structured profile.

Steps: (1) extract text locally (no LLM); (2) one-shot zero-invention structured parse into our
profile.json shape; (3) deterministic thin-parse detection -> the questions to ask the user; (4)
save the parsed profile to the run dir (applying to the canonical profile.json is an explicit,
separate action so a demo never clobbers a real profile).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from resumaker.providers.llm import get_provider

from . import store
from .prompts import GUARDRAIL, INTAKE_PARSE
from .questions import PREFERENCE_QUESTIONS

OUTCOME_VERBS = ("improved", "reduced", "increased", "cut", "boosted", "accelerated", "saved",
                 "grew", "decreased", "optimized", "scaled", "drove", "raised", "lowered")


def extract_text(path: str) -> str:
    """Local text extraction (no LLM). PDF via the existing resume renderer; docx/txt read directly."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        from resumaker.stages.resume.render_pdf import extract_text as pdf_text
        return pdf_text(str(p))
    if suffix == ".docx":
        from docx import Document  # python-docx, already a dep for rendering
        return "\n".join(par.text for par in Document(str(p)).paragraphs)
    return p.read_text(encoding="utf-8", errors="ignore")


def detect_thin_spots(profile: dict) -> list[str]:
    """Deterministic completeness checks (no LLM). Returns human-readable thin spots to probe."""
    spots: list[str] = []
    if not (profile.get("summary") or "").strip():
        spots.append("No professional summary yet - add a 2-3 line summary.")
    for exp in profile.get("experience", []):
        label = f"{exp.get('title','?')} @ {exp.get('organization','?')}"
        bullets = exp.get("bullets", [])
        if not bullets:
            spots.append(f"'{label}' has no bullet points describing what you did.")
            continue
        for b in bullets:
            text = (b.get("text") or "").lower()
            if not b.get("metrics") and any(v in text for v in OUTCOME_VERBS):
                spots.append(f"'{label}': a bullet describes an outcome but has no metric "
                             f"({b.get('text','')[:60]}...). What measurably changed?")
                break
    if len([g for g in (profile.get("skills") or {}).values() for _ in g]) < 6:
        spots.append("Your skills list looks short - which languages/frameworks/clouds have you used?")
    if not profile.get("work_authorization"):
        spots.append("Work authorization is unset - do you need visa sponsorship now or later?")
    return spots


def extract_upload(raw: bytes, filename: str) -> str:
    """Extract text from an uploaded file's bytes (PDF/DOCX/TXT) by writing to a temp file and reusing
    the local extractors. No LLM. Raises ValueError if nothing readable comes out."""
    import tempfile
    suffix = Path(filename or "").suffix.lower() or ".txt"
    if suffix not in (".pdf", ".docx", ".txt", ".md"):
        raise ValueError(f"unsupported file type {suffix!r} - upload a PDF, DOCX, or TXT")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(raw)
        tmp.flush()
        text = extract_text(tmp.name)
    if len((text or "").strip()) < 40:
        raise ValueError("couldn't read text from that file - it may be scanned/image-only; "
                         "try a text-based PDF/DOCX or paste the text")
    return text


def parse_resume(text: str, *, llm: Any = None) -> tuple[dict, list[str]]:
    """Parse resume text into a profile-shaped dict (LLM, zero-invention) and return (profile,
    thin_spots). Does NOT persist. Raises ValueError if the text is too short or yields no profile."""
    if len((text or "").strip()) < 40:
        raise ValueError("that doesn't look like resume text - too short to parse")
    llm = llm or get_provider("claude", model="sonnet")
    parsed = llm.complete_json(INTAKE_PARSE.format(guardrail=GUARDRAIL, resume_text=text[:20000]),
                               task="profile-intake")
    if not isinstance(parsed, dict) or not (
            parsed.get("experience") or parsed.get("projects") or parsed.get("skills")):
        raise ValueError("couldn't extract a profile from that text - is it a resume?")
    parsed.setdefault("facts_allowlist", {})
    parsed["facts_allowlist"].setdefault(
        "employers", sorted({e.get("organization", "") for e in parsed.get("experience", []) if e.get("organization")}))
    parsed["facts_allowlist"].setdefault(
        "titles", sorted({e.get("title", "") for e in parsed.get("experience", []) if e.get("title")}))
    return parsed, detect_thin_spots(parsed)


def run_intake(resume_path: str, *, linkedin_path: str | None = None, llm: Any = None) -> store.RunState:
    """Parse a resume (+ optional LinkedIn PDF) into a profile.json-shaped dict, detect thin spots,
    and stash the result in the run dir. Returns the run state (state=needs_input if thin spots or
    preferences remain to be asked)."""
    st = store.new_run("intake", resume_path=resume_path, linkedin_path=linkedin_path or "")
    text = extract_text(resume_path)
    if linkedin_path:
        text += "\n\n=== LINKEDIN EXPORT ===\n" + extract_text(linkedin_path)
    return _parse_into_run(st, text, llm)


def run_intake_text(text: str, *, llm: Any = None) -> store.RunState:
    """Same as run_intake but from pasted resume text (used by the web UI - no file upload)."""
    st = store.new_run("intake", resume_path="(pasted text)")
    return _parse_into_run(st, text, llm)


def _parse_into_run(st: store.RunState, text: str, llm: Any) -> store.RunState:
    llm = llm or get_provider("claude", model="sonnet")
    st.add_event("extract", "ok", f"{len(text)} chars of source text")

    parsed = llm.complete_json(INTAKE_PARSE.format(guardrail=GUARDRAIL, resume_text=text[:20000]),
                               task="profile-intake")
    if not isinstance(parsed, dict):
        st.state = "error"
        st.add_event("parse", "error", "parser did not return an object")
        store.save(st)
        return st

    # seed the fact-gate allowlist from the parsed structure so later generation recognizes them
    parsed.setdefault("facts_allowlist", {})
    parsed["facts_allowlist"].setdefault(
        "employers", sorted({e.get("organization", "") for e in parsed.get("experience", []) if e.get("organization")}))
    parsed["facts_allowlist"].setdefault(
        "titles", sorted({e.get("title", "") for e in parsed.get("experience", []) if e.get("title")}))

    out = store.runs_dir() / st.run_id / "parsed_profile.json"
    out.write_text(json.dumps(parsed, indent=2))
    st.meta["parsed_profile"] = str(out)
    st.add_event("parse", "ok", f"{len(parsed.get('experience', []))} roles, "
                                f"{len(parsed.get('projects', []))} projects")

    thin = detect_thin_spots(parsed)
    prefs = [q["q"] for q in PREFERENCE_QUESTIONS]
    st.meta["thin_spots"] = thin
    st.meta["preferences_to_ask"] = prefs
    # there's always at least the preference questions to ask, so intake ends in needs_input
    st.state = "needs_input" if (thin or prefs) else "done"
    st.add_event("review", "needs_input",
                 f"{len(thin)} thin spot(s); {len(prefs)} preference questions")
    store.save(st)
    return st


def apply_parsed_to_profile(run_id: str) -> None:
    """Explicit, separate action: promote a run's parsed_profile.json to the canonical profile.json.
    Kept separate so parsing/demoing never clobbers an existing real profile by accident."""
    from resumaker.persistence import profile as profile_store
    st = store.load(run_id)
    parsed = json.loads(Path(st.meta["parsed_profile"]).read_text())
    profile_store.save_profile(parsed)
    st.add_event("apply", "ok", "parsed profile promoted to canonical profile.json")
    store.save(st)
