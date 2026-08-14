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


# ---------------------------------------------------------------- first-time deterministic seed
def is_seeded() -> bool:
    """True if a real profile already exists, so a first-time seed knows to confirm before it would
    overwrite one."""
    d = load_profile()
    return bool(d.get("experience") or d.get("projects") or d.get("skills")
                or (d.get("contact") or {}).get("name"))


def profile_template() -> dict:
    """A blank profile document in the canonical schema, one example entry per section, for a
    deterministic first-time seed (no LLM, lossless). Fill it in and POST to /v1/profile/seed. Unlike
    the resume parser, this preserves hand-curated structure (equivalence_map, target_archetypes)."""
    return {
        "_help": ("Fill this in and seed it deterministically (no AI parsing). Delete this _help key. "
                  "skills is grouped by category. dates are free text, e.g. 'Jan 2024 - Aug 2024'. "
                  "Leave anything you don't have as an empty string / list."),
        "contact": {"name": "", "email": "", "phone": "", "location": ""},
        "links": {"portfolio": "", "linkedin": "", "github": ""},
        "work_authorization": {"status": "", "needs_sponsorship": False},
        "target_archetypes": ["AI/ML Engineer", "Software Engineer"],
        "summary": "2-3 line professional summary.",
        "experience": [{
            "title": "Job Title", "organization": "Company", "location": "City, ST",
            "start_date": "Jan 2024", "end_date": "Aug 2024", "is_current": False,
            "bullets": [{"text": "What you did and the measurable outcome.",
                         "metrics": ["40%"], "skills_used": ["Python"]}],
        }],
        "projects": [{"title": "Project Name", "organization": "", "date": "2025", "url": "",
                      "bullets": [{"text": "What you built and its impact."}]}],
        "education": [{"degree": "MS in ...", "institution": "University", "location": "City, ST",
                       "dates": "2024 - 2026"}],
        "skills": {"Languages": ["Python", "SQL"], "Frameworks": ["FastAPI"],
                   "Cloud & Data": ["GCP", "Snowflake"]},
        "certifications": [], "awards": [], "languages": [],
        "equivalence_map": {"_note": "owned_tool -> [equivalent tools you can honestly bridge to]"},
    }


def _coerce_bullets(bullets: object) -> list[dict]:
    """Normalize a bullets list into [{text, metrics?, skills_used?}], tolerating plain strings and
    dropping empties - so a malformed paste can't leave the pipeline reading b['text'] on a string."""
    out: list[dict] = []
    for b in bullets if isinstance(bullets, list) else []:
        if isinstance(b, dict) and str(b.get("text", "")).strip():
            item = {"text": str(b["text"]).strip()}
            if isinstance(b.get("metrics"), list):
                item["metrics"] = [str(m) for m in b["metrics"]]
            if isinstance(b.get("skills_used"), list):
                item["skills_used"] = [str(s) for s in b["skills_used"]]
            out.append(item)
        elif isinstance(b, str) and b.strip():
            out.append({"text": b.strip()})
    return out


def _normalize_profile(doc: dict) -> dict:
    """Coerce a (possibly messy) profile doc into the shape the pipeline relies on: experience/projects
    are lists of dicts with the expected keys and clean bullets; skills is category -> list[str].
    Non-dict entries are dropped rather than left to crash tailoring/rendering downstream."""
    d = dict(doc)
    if isinstance(d.get("experience"), list):
        exp = []
        for e in d["experience"]:
            if not isinstance(e, dict):
                continue
            e = dict(e)
            e["bullets"] = _coerce_bullets(e.get("bullets"))
            for k in ("title", "organization", "location", "start_date", "end_date"):
                e.setdefault(k, "")
            exp.append(e)
        d["experience"] = exp
    if isinstance(d.get("projects"), list):
        projs = []
        for p in d["projects"]:
            if not isinstance(p, dict):
                continue
            p = dict(p)
            p["bullets"] = _coerce_bullets(p.get("bullets"))
            for k in ("title", "organization", "date", "url"):
                p.setdefault(k, "")
            projs.append(p)
        d["projects"] = projs
    if isinstance(d.get("skills"), dict):
        d["skills"] = {str(k): [str(x) for x in v if str(x).strip()]
                       for k, v in d["skills"].items() if isinstance(v, list)}
    return d


def seed_profile(doc: dict) -> dict:
    """Deterministically load a full profile document (no LLM) into the canonical store. Validates the
    shape, normalizes messy/garbage entries, stamps _meta, saves via save_profile (DB), and returns a
    small summary. Raises ValueError if the doc isn't a usable profile."""
    if not isinstance(doc, dict):
        raise ValueError("profile must be a JSON object")
    for key, typ, label in (("experience", list, "list"), ("projects", list, "list"),
                            ("skills", dict, "object")):
        if key in doc and not isinstance(doc[key], typ):
            raise ValueError(f"'{key}' must be a JSON {label}")
    doc = {k: v for k, v in doc.items() if k != "_help"}     # drop template guidance if left in
    doc = _normalize_profile(doc)
    if not (doc.get("experience") or doc.get("projects") or doc.get("skills")):
        raise ValueError("profile is empty - fill in at least experience, projects, or skills")
    meta = dict(doc.get("_meta") or {})
    meta["seeded"] = datetime.datetime.now().isoformat(timespec="seconds")
    doc["_meta"] = meta
    save_profile(doc)
    n_skills = sum(len(v) for v in (doc.get("skills") or {}).values() if isinstance(v, list))
    return {"experience": len(doc.get("experience") or []),
            "projects": len(doc.get("projects") or []), "skills": n_skills}


def save_preferences(data: dict) -> None:
    from resumaker.persistence import db
    db.put_document("preferences", data)
    invalidate()


# The full email-digest control set (the Mailer page). One doc, so the old mailer_filter
# (title include/exclude) is just a subset of this.
# No email overnight by default: the digest defers 12am-8am local and sends the backlog at 8am.
_QUIET_DEFAULT = ("00:00", "08:00")

MAILER_DEFAULTS: dict = {
    "include": [], "exclude": [],        # title has-ANY / has-NONE
    "levels": [], "states": [],          # seniority + US-state filters (empty = all)
    "quiet_enabled": True,               # master switch; False = never quiet (email 24/7)
    "quiet_start": _QUIET_DEFAULT[0], "quiet_end": _QUIET_DEFAULT[1],  # "HH:MM" local quiet window
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
    merged = {**MAILER_DEFAULTS, **doc}
    # When quiet hours are enabled but the window is unconfigured (an older doc, or the previous
    # empty default), fall back to the overnight window so it applies without a manual re-save. A
    # custom window is preserved. To turn quiet hours OFF entirely, set quiet_enabled=False (the
    # window is then ignored) - that's how the owner keeps a "never quiet, email 24/7" option.
    if merged.get("quiet_enabled") and not (
            str(merged.get("quiet_start") or "").strip() and str(merged.get("quiet_end") or "").strip()):
        merged["quiet_start"], merged["quiet_end"] = _QUIET_DEFAULT
    return merged


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
