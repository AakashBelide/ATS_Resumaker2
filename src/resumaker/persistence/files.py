"""Run-artifact file store. Files are canonical (the DB only indexes them).

A run gets a slug directory under `settings.output_dir` (e.g. `state-street-ai-...`).
Callers write JD.txt, content.json, the .docx/.pdf, report.json, status.json, etc.
there. Kept dependency-free and deterministic so the same JD maps to the same dir.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from resumaker.config import get_settings


def slugify(*parts: str) -> str:
    """ASCII kebab slug from arbitrary text parts (company, role...)."""
    text = " ".join(p for p in parts if p)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", text) or "run"


def run_slug(company: str = "", role: str = "", fallback: str = "", unique_key: str = "") -> str:
    """Kebab slug from company+role (or `fallback`). When `unique_key` is given (the posting URL
    or external_id), append a short stable hash so two same-titled postings don't collide on the
    same run dir / report URL, e.g. `snowflake-solution-engineer-a1b2c3`. Kept deterministic: the
    same key always yields the same suffix, so re-runs of one posting reuse its dir."""
    base = slugify(company, role) if (company or role) else (slugify(fallback) or "run")
    if unique_key:
        return f"{base}-{hashlib.sha1(unique_key.encode('utf-8')).hexdigest()[:6]}"
    return base


def run_dir(slug: str, *, create: bool = True) -> Path:
    d = get_settings().output_root / slug
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
