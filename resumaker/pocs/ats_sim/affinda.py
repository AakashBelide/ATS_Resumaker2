"""Independent industry parse oracle via Affinda (Phase 3.4).

Sends the generated resume PDF to Affinda's resume parser (Textkernel-class, the
same category of engine real ATS use) and reports the fields it extracts, diffed
against what we intended (the profile). This is the most credible answer to "does
my resume actually parse into clean ATS fields?" - independent of our own parser.

Setup (owner, one-time; free tier):
  1. Sign up at https://app.affinda.com and create an API key.
  2. Create a Collection using the "Resume Parser" extractor; copy its id.
  3. In .env (gitignored):  AFFINDA_API_KEY=...   AFFINDA_COLLECTION=...

Run:  uv run python -m pocs.ats_sim.affinda [path/to/resume.pdf]
Cost: Affinda's free tier (no charge to this project; no Gemini budget impact).
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

from core import profile as prof

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_PDF = (_REPO / "outputs" / "state-street-ai-orchestration-engineer" /
                "state-street-ai-orchestration-engineer.pdf")
_API = "https://api.affinda.com/v3/documents"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(_REPO / ".env")
    except Exception:  # noqa: BLE001
        pass


def parse_with_affinda(pdf_path: str) -> dict:
    """Return Affinda's parsed resume `data` dict. Raises if not configured."""
    _load_env()
    key = os.getenv("AFFINDA_API_KEY")
    if not key:
        raise RuntimeError(
            "AFFINDA_API_KEY not set. Add it (and AFFINDA_COLLECTION) to .env - "
            "see .env.example / this module's docstring.")
    data = {"wait": "true"}
    if os.getenv("AFFINDA_COLLECTION"):
        data["collection"] = os.getenv("AFFINDA_COLLECTION")
    with open(pdf_path, "rb") as fh:
        r = httpx.post(_API, headers={"Authorization": f"Bearer {key}"},
                       files={"file": (Path(pdf_path).name, fh, "application/pdf")},
                       data=data, timeout=120)
    r.raise_for_status()
    return r.json().get("data", {}) or {}


def _card(d: dict) -> dict:
    """Normalize Affinda's response into a comparable parse card."""
    def _txt(x):
        return x.get("raw") if isinstance(x, dict) else x
    work = d.get("workExperience", []) or []
    return {
        "name": _txt((d.get("name") or {}).get("raw") if isinstance(d.get("name"), dict) else d.get("name")),
        "emails": d.get("emails", []) or d.get("email", []),
        "phones": d.get("phoneNumbers", []) or [],
        "location": (d.get("location") or {}).get("formatted", "") if isinstance(d.get("location"), dict) else d.get("location", ""),
        "employers": [w.get("organization") for w in work if w.get("organization")],
        "titles": [w.get("jobTitle") for w in work if w.get("jobTitle")],
        "skills": [s.get("name") if isinstance(s, dict) else s for s in (d.get("skills", []) or [])],
        "education": [(e.get("organization") or (e.get("accreditation") or {}).get("education"))
                      for e in (d.get("education", []) or [])],
    }


def affinda_report(pdf_path: str | None = None) -> dict:
    """Parse via Affinda and diff against the profile (what we intended)."""
    pdf_path = pdf_path or str(_DEFAULT_PDF)
    card = _card(parse_with_affinda(pdf_path))
    prof_emps = {e.lower() for e in prof.all_employers()}
    got_emps = {(e or "").lower() for e in card["employers"]}
    missed_emps = sorted(e for e in prof_emps
                         if not any(e in g or g in e for g in got_emps if g))
    captured = {k: bool(v) for k, v in card.items()}
    return {
        "pdf": pdf_path,
        "parsed": card,
        "captured_fields": captured,
        "employers_missed_by_parser": missed_emps,
        "n_skills_parsed": len(card["skills"]),
        "parse_ok": all([card["name"], card["emails"], card["location"],
                         card["employers"], card["skills"]]),
    }


if __name__ == "__main__":
    import json
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        rep = affinda_report(path)
        print(json.dumps(rep, indent=1, default=str))
    except RuntimeError as e:
        print(f"[not configured] {e}")
