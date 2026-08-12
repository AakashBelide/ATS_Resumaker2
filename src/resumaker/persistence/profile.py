"""Loader + helpers for the canonical candidate profile (single source of truth).

Everything the pipeline generates must trace back to this. The fact-gate uses
`all_metrics/all_employers/all_titles` + `facts_allowlist` to block fabrication.

The profile/preferences live in the DB (dual-mode: local SQLite or hosted Turso) so the cloud
services can read them and they're editable in-app. On first read, a legacy JSON file under
`data/profile/` is auto-imported into the DB, so existing local setups migrate transparently.
"""
from __future__ import annotations

import contextlib
import datetime
import functools
import json
import re
from pathlib import Path

from resumaker.config import get_settings


def _load_doc(name: str, file_path: Path, default: dict) -> dict:
    """Read a config document from the DB, auto-migrating the legacy JSON file on first read."""
    from resumaker.persistence import db
    doc = db.get_document(name)
    if doc is not None:
        return doc
    if file_path.exists():                       # first run: import the file into the DB
        data = json.loads(file_path.read_text())
        with contextlib.suppress(Exception):     # best-effort cache (DB may lack the table yet)
            db.put_document(name, data)
        return data
    return default


@functools.lru_cache(maxsize=1)
def load_profile() -> dict:
    return _load_doc("profile", get_settings().profile_path, default={})


@functools.lru_cache(maxsize=1)
def load_preferences() -> dict:
    """Job-search preferences: target roles, comp, location (incl. relocation metros),
    work-model, seniority, sponsorship. Returns {} if not yet configured."""
    return _load_doc("preferences", get_settings().preferences_path, default={})


def save_profile(data: dict) -> None:
    """Persist an edited profile to the DB and refresh caches (used by the API editor)."""
    from resumaker.persistence import db
    db.put_document("profile", data)
    invalidate()


def save_preferences(data: dict) -> None:
    from resumaker.persistence import db
    db.put_document("preferences", data)
    invalidate()


# The full email-digest control set (the Mailer page). One doc, so the old mailer_filter
# (title include/exclude) is just a subset of this.
MAILER_DEFAULTS: dict = {
    "include": [], "exclude": [],        # title has-ANY / has-NONE
    "levels": [], "states": [],          # seniority + US-state filters (empty = all)
    "quiet_start": "", "quiet_end": "",  # "HH:MM" local; empty pair = no quiet window
    "timezone": "America/New_York",      # tz the quiet window is interpreted in
    "max_postings": 0,                   # cap per digest (0 = no cap); rest shown as "X of N"
    "frequency": "hourly",               # digest cadence -> Cloud Scheduler (Mailer page)
}


def load_mailer_prefs() -> dict:
    """All email-digest controls, with defaults filled in. Migrates a legacy `mailer_filter`
    doc's include/exclude on first read."""
    from resumaker.persistence import db
    doc = db.get_document("mailer_prefs")
    if doc is None:
        legacy = db.get_document("mailer_filter") or {}
        return {**MAILER_DEFAULTS, "include": legacy.get("include") or [],
                "exclude": legacy.get("exclude") or []}
    return {**MAILER_DEFAULTS, **doc}


def save_mailer_prefs(data: dict) -> None:
    """Persist the mailer controls (merges onto current, only known keys)."""
    from resumaker.persistence import db
    merged = {**load_mailer_prefs(), **{k: v for k, v in data.items() if k in MAILER_DEFAULTS}}
    db.put_document("mailer_prefs", merged)


def load_mailer_filter() -> dict:
    """Title include/exclude subset (kept for the Profile mailer editor + notify)."""
    p = load_mailer_prefs()
    return {"include": p["include"], "exclude": p["exclude"]}


def save_mailer_filter(data: dict) -> None:
    save_mailer_prefs({"include": list(data.get("include") or []),
                       "exclude": list(data.get("exclude") or [])})


def invalidate() -> None:
    """Drop cached profile/preferences after an update writes to the DB."""
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
    ('3+ years'); else the span from the earliest experience start."""
    p = load_profile()
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years", p.get("summary", "") or "")
    if m:
        return float(m.group(1))
    years: list[int] = []
    for e in p.get("experience", []):
        m2 = re.search(r"(19|20)\d{2}", e.get("start_date", "") or "")
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
        parts.append(f"- {ed['title']}, {ed['organization']} (GPA {ed.get('gpa','n/a')})")
    return "\n".join(x for x in parts if x is not None)
