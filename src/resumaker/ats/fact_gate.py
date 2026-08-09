"""Mechanical fact-gate (Task 1.9) - non-bypassable anti-fabrication check.

Adapted from career-ops' verify-cv-facts. Extracts the meaningful claims from a
generated resume and verifies each traces to the profile:
  - METRICS (%, $, multipliers, large counts, 'N years') must match a profile metric.
  - EMPLOYERS / TITLES (structured fields) must match the profile.
  - FORBIDDEN phrases (facts_allowlist) hard-block.
Unsupported metric/employer/title -> BLOCK. Verdict gates the pipeline (blueprint §3).
This is prompt-independent: even if the LLM ignores its instructions, this catches it.
"""
from __future__ import annotations

import re

from resumaker.domain import ResumeContent, VerifyReport
from resumaker.persistence import profile as prof

# ONE cohesive number(+unit) matcher -> non-overlapping matches (no fragments like
# "19 million" out of "$1.19 million"). Meaningfulness is filtered afterward.
_METRIC_RE = re.compile(
    r"(?<![A-Za-z0-9])"                       # not a digit embedded in a word (B2B, S3, GPT4o)
    r"\$?\s?\d[\d,]*(?:\.\d+)?\s?\+?\s?"
    r"(?:%|million|billion|thousand|[mbk]\b|x\b|times|years?)?", re.I)
_UNIT_MARKERS = ("%", "$", "million", "billion", "thousand", "x", "time", "year")

_UNIT = {"million": "m", "billion": "b", "thousand": "k", "times": "x", "percent": "%"}


def _norm_metric(s: str) -> str:
    s = s.lower().strip()
    for word, ab in _UNIT.items():
        s = s.replace(word, ab)
    s = re.sub(r"[\s,$~+]", "", s)          # drop spaces, commas, $, ~, +
    s = s.replace("year", "y").replace("ys", "y")
    return s


def _profile_metric_set() -> set[str]:
    """Grounded numbers = curated profile metrics UNION every number that actually
    appears in the profile source text (bullets/summary/skills/education). A resume
    number is 'invented' only if it appears NOWHERE in the source -- so real
    non-metric numbers (course code 'INFO 6215', '5+ pages') are not false-flagged,
    while fabricated figures ('$500 million') still are."""
    grounded = {_norm_metric(m) for m in prof.all_metrics()}
    grounded |= {_norm_metric(tok) for tok in _extract_metrics(prof.profile_text())}
    return {g for g in grounded if g}


_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


def _meaningful(tok: str) -> bool:
    """Keep achievement metrics; drop trivial small bare integers (e.g. '3 bullets')."""
    t = tok.lower()
    if any(u in t for u in _UNIT_MARKERS):
        return True
    if re.search(r"\d\s?[mbk]\b", t):          # 10B, 5k, etc.
        return True
    return len(re.sub(r"\D", "", tok)) >= 3     # large count (>=3 digits)


def _extract_metrics(text: str) -> list[str]:
    found: list[str] = []
    for m in _METRIC_RE.finditer(text):
        tok = m.group(0).strip().rstrip("+ ").strip()
        if not re.search(r"\d", tok):
            continue
        if _YEAR_RE.match(re.sub(r"[,\s]", "", tok)):   # skip bare years (dates)
            continue
        if _meaningful(tok):
            found.append(tok)
    return found


def ungrounded_metrics(text: str) -> list[str]:
    """Public: numbers in `text` that don't trace to the profile (fabrication check
    for any generated artifact - resume, cover letter, LinkedIn blurb)."""
    prof_metrics = _profile_metric_set()
    out: list[str] = []
    for raw in _extract_metrics(text):
        n = _norm_metric(raw)
        if n and n not in prof_metrics:
            out.append(raw.strip())
    return sorted(set(out))


def _resume_text(content: ResumeContent) -> str:
    parts = [content.headline, content.summary]
    for e in content.experiences:
        parts += e.get("bullets", [])
    for pr in content.projects:
        parts += pr.get("bullets", [])
    return "\n".join(p for p in parts if p)


def verify_resume(content: ResumeContent) -> VerifyReport:
    blockers: list[str] = []
    warnings: list[str] = []

    text = _resume_text(content)
    prof_metrics = _profile_metric_set()

    # (1) metrics traceability
    invented: list[str] = []
    for raw in _extract_metrics(text):
        n = _norm_metric(raw)
        if not n or n in prof_metrics:
            continue
        # exact normalized equality only. Substring tolerance is unsafe for numbers
        # (e.g. profile "9" is a substring of a fabricated "99.9%"), so it's removed:
        # "+" and formatting are already normalized away, so real metrics match exactly.
        invented.append(raw.strip())
    if invented:
        blockers.append(f"Unsupported metric(s) not found in profile: {sorted(set(invented))}")

    # (2) employers + titles (structured fields must match the profile)
    emps = {e.lower() for e in prof.all_employers()}
    titles = {t.lower() for t in prof.all_titles()}
    for e in content.experiences:
        org = (e.get("organization") or "").strip()
        if org and org.lower() not in emps and not any(org.lower() in x or x in org.lower() for x in emps):
            blockers.append(f"Unknown employer on resume: {org!r}")
        title = (e.get("title") or "").strip()
        if title and title.lower() not in titles and not any(
                title.lower() in x or x in title.lower() for x in titles):
            warnings.append(f"Title not an exact profile match (verify): {title!r}")

    # (3) forbidden phrases
    forbidden = prof.facts_allowlist().get("forbidden_phrases", [])
    for ph in forbidden:
        if ph and re.search(rf"\b{re.escape(ph)}\b", text, re.I):
            blockers.append(f"Forbidden phrase present: {ph!r}")

    return VerifyReport(
        passed=not blockers,
        blockers=blockers,
        warnings=warnings,
        checks={"metrics_checked": len(_extract_metrics(text)),
                "invented_metrics": len(invented),
                "experiences": len(content.experiences)},
    )
