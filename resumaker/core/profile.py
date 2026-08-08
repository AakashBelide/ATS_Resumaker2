"""Loader + helpers for the canonical candidate profile (single source of truth).

Everything the pipeline generates must trace back to this. The fact-gate (Task 1.9)
uses `all_metrics/all_employers/all_titles` + `facts_allowlist` to block fabrication.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "data" / "profile" / "profile.json"
PREFERENCES_PATH = REPO_ROOT / "data" / "profile" / "preferences.json"


@functools.lru_cache(maxsize=1)
def load_profile() -> dict:
    with PROFILE_PATH.open() as fh:
        return json.load(fh)


@functools.lru_cache(maxsize=1)
def load_preferences() -> dict:
    """Job-search preferences (Task 1.13): target roles, comp, location,
    work-model, seniority, sponsorship. Separate from the resume-fact profile.
    Returns {} if not yet configured (pipeline then uses safe defaults)."""
    if not PREFERENCES_PATH.exists():
        return {}
    with PREFERENCES_PATH.open() as fh:
        return json.load(fh)


def invalidate() -> None:
    """Drop cached profile/preferences after an enrichment update writes to disk."""
    load_profile.cache_clear()
    load_preferences.cache_clear()


def equivalence_map() -> dict[str, list[str]]:
    m = dict(load_profile().get("equivalence_map", {}))
    m.pop("_note", None)
    return m


def facts_allowlist() -> dict:
    return load_profile().get("facts_allowlist", {})


def all_bullets() -> list[str]:
    p = load_profile()
    out: list[str] = []
    for exp in p.get("experience", []):
        out += [b["text"] for b in exp.get("bullets", [])]
    for proj in p.get("projects", []):
        out += [b["text"] for b in proj.get("bullets", [])]
    return out


def all_metrics() -> set[str]:
    p = load_profile()
    metrics: set[str] = set()
    for exp in p.get("experience", []):
        for b in exp.get("bullets", []):
            metrics.update(b.get("metrics", []))
    for proj in p.get("projects", []):
        for b in proj.get("bullets", []):
            metrics.update(b.get("metrics", []))
    metrics.update(facts_allowlist().get("headline_metrics", []))
    return metrics


def all_employers() -> set[str]:
    p = load_profile()
    emps = {e.get("organization", "") for e in p.get("experience", [])}
    emps.update(facts_allowlist().get("employers", []))
    return {e for e in emps if e}


def all_titles() -> set[str]:
    p = load_profile()
    titles = {e.get("title", "") for e in p.get("experience", [])}
    titles.update(facts_allowlist().get("titles", []))
    return {t for t in titles if t}


def all_skills() -> set[str]:
    p = load_profile()
    skills: set[str] = set()
    for group in p.get("skills", {}).values():
        skills.update(group)
    return skills


def needs_sponsorship() -> bool:
    return bool(load_profile().get("work_authorization", {})
               .get("needs_sponsorship_future", False))


def candidate_years() -> float:
    """Years of professional experience. Prefer the stated figure in the summary
    ('3+ years'); else fall back to the span from earliest experience start."""
    import datetime
    import re as _re
    p = load_profile()
    m = _re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years", p.get("summary", "") or "")
    if m:
        return float(m.group(1))
    years: list[int] = []
    for e in p.get("experience", []):
        m2 = _re.search(r"(19|20)\d{2}", e.get("start_date", "") or "")
        if m2:
            years.append(int(m2.group(0)))
    if years:
        return round(datetime.date.today().year - min(years), 1)
    return 0.0


def profile_text() -> str:
    """Flattened text blob of the whole profile, for LLM grounding prompts."""
    p = load_profile()
    parts: list[str] = [f"# {p['contact']['name']}", p.get("summary", ""), ""]
    parts.append("## Experience")
    for e in p.get("experience", []):
        parts.append(f"### {e['title']} - {e['organization']} "
                     f"({e.get('start_date','')} - {e.get('end_date','')})")
        parts += [f"- {b['text']}" for b in e.get("bullets", [])]
    parts.append("\n## Projects")
    for pr in p.get("projects", []):
        parts.append(f"### {pr['title']} ({pr.get('date','')})")
        parts += [f"- {b['text']}" for b in pr.get("bullets", [])]
    parts.append("\n## Skills")
    for cat, items in p.get("skills", {}).items():
        parts.append(f"- {cat}: {', '.join(items)}")
    parts.append("\n## Education")
    for ed in p.get("education", []):
        parts.append(f"- {ed['title']}, {ed['organization']} "
                     f"(GPA {ed.get('gpa','n/a')})")
    return "\n".join(x for x in parts if x is not None)


if __name__ == "__main__":
    print(f"employers: {sorted(all_employers())}")
    print(f"titles:    {sorted(all_titles())}")
    print(f"#metrics:  {len(all_metrics())}  #skills: {len(all_skills())}")
    print(f"equiv keys: {list(equivalence_map())[:5]}...")
