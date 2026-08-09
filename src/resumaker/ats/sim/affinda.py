"""Independent industry parse oracle via Affinda (Phase 3.4).

Sends the generated resume PDF to Affinda's resume parser (Textkernel-class, the
same category of engine real ATS use) and reports the fields it extracts, diffed
against what we intended (the profile). This is the most credible answer to "does
my resume actually parse into clean ATS fields?" - independent of our own parser.

Setup (owner, one-time; free tier). Affinda organizes uploads by WORKSPACE +
document type (not "collections"):
  1. Sign up at https://app.affinda.com and create an API key.
  2. Use your workspace's identifier (shown in the Affinda UI/assistant).
  3. In .env (gitignored):  AFFINDA_API_KEY=...   AFFINDA_WORKSPACE=<workspace id>
     (optional AFFINDA_DOCUMENT_TYPE=<doc-type id> to force the Resume schema;
      legacy AFFINDA_COLLECTION is still honored for older accounts.)

Run:  uv run python -m pocs.ats_sim.affinda [path/to/resume.pdf]
Cost: Affinda's free tier (no charge to this project; no Gemini budget impact).
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

import httpx

from resumaker.config import get_settings

_DEFAULT_PDF = (get_settings().output_root / "state-street-ai-orchestration-engineer" /
                "state-street-ai-orchestration-engineer.pdf")
# Affinda is region-scoped: api.affinda.com (APAC, default) | api.us1.affinda.com (US)
# | api.eu1.affinda.com (EU). A token only authenticates against its account's region.
_DEFAULT_BASE = "https://api.affinda.com"


def _api_url() -> str:
    base = os.getenv("AFFINDA_BASE_URL") or _DEFAULT_BASE
    return base.rstrip("/") + "/v3/documents"


def _load_env() -> None:
    # Affinda keys are optional/validation-only, so they live in .env (not Settings).
    with contextlib.suppress(Exception):
        from dotenv import load_dotenv
        load_dotenv(get_settings().root_dir / ".env")


def parse_with_affinda(pdf_path: str) -> dict:
    """Return Affinda's parsed resume `data` dict. Raises if not configured."""
    _load_env()
    key = os.getenv("AFFINDA_API_KEY")
    if not key:
        raise RuntimeError(
            "AFFINDA_API_KEY not set. Add it (and AFFINDA_WORKSPACE) to .env - "
            "see .env.example / this module's docstring.")
    # Affinda routes by workspace + document type (newer model) or collection (legacy).
    data = {"wait": "true"}
    if os.getenv("AFFINDA_WORKSPACE"):
        data["workspace"] = os.getenv("AFFINDA_WORKSPACE")
    if os.getenv("AFFINDA_DOCUMENT_TYPE"):
        data["documentType"] = os.getenv("AFFINDA_DOCUMENT_TYPE")
    if os.getenv("AFFINDA_COLLECTION"):
        data["collection"] = os.getenv("AFFINDA_COLLECTION")
    if not any(k in data for k in ("workspace", "collection")):
        raise RuntimeError(
            "Set AFFINDA_WORKSPACE (recommended) or AFFINDA_COLLECTION in .env.")
    with open(pdf_path, "rb") as fh:
        r = httpx.post(_api_url(), headers={"Authorization": f"Bearer {key}"},
                       files={"file": (Path(pdf_path).name, fh, "application/pdf")},
                       data=data, timeout=120)
    r.raise_for_status()
    return r.json().get("data", {}) or {}


def _leaf(x):
    """Affinda leaf fields are {raw, parsed, confidence,...}; pull a readable value."""
    if isinstance(x, dict):
        p = x.get("parsed")
        if isinstance(p, (str, int, float)):
            return p
        if isinstance(p, dict):
            return p.get("formatted") or p.get("rawText") or p.get("name") or x.get("raw")
        return x.get("raw")
    return x


def _card(d: dict) -> dict:
    """Normalize Affinda's resume schema into a readable parse card. Work/education/
    project entries come back as grouped `raw` text blocks in this workspace config."""
    def blocks(key):
        return [_leaf(it) for it in (d.get(key) or []) if _leaf(it)]
    return {
        "name": _leaf(d.get("candidateName")),
        "emails": [_leaf(e) for e in (d.get("email") or [])],
        "phones": [_leaf(p) for p in (d.get("phoneNumber") or [])],
        "location": _leaf(d.get("location")),
        "total_years_experience": _leaf(d.get("totalYearsExperience")),
        "experience": blocks("workExperience"),
        "projects": blocks("project"),
        "education": blocks("education"),
        "skills": [_leaf(s) for s in (d.get("skill") or [])],
    }


def affinda_report(pdf_path: str | None = None) -> dict:
    """Parse via Affinda (independent oracle) and summarize what it captured."""
    pdf_path = pdf_path or str(_DEFAULT_PDF)
    card = _card(parse_with_affinda(pdf_path))
    key_fields = ["name", "emails", "location", "experience", "education", "skills"]
    return {
        "pdf": pdf_path,
        "parsed": card,
        "captured": {k: bool(card.get(k)) for k in key_fields},
        "n_skills_parsed": len(card["skills"]),
        "parse_ok": all(card.get(k) for k in key_fields),
    }
