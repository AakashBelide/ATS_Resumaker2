"""Enrichment proposals (RA.3): mine the tracked jobs' match artifacts for signals that the
profile should be enriched - the keystone loop, since match quality is capped by profile
completeness.

Honest by construction: we NEVER auto-add anything, and we separate two very different
signals from each tracked job's gap report:
  - `have_but_unlisted` - requirements the gap analysis judged `supportedByResume` (there IS
    profile evidence for them) that aren't an explicit profile skill. Safe to surface as
    "you have this; consider listing it."
  - `recurring_gaps` - requirements classified as a true `gap`. Surfaced for AWARENESS only;
    the owner adds one ONLY if they actually have it (the incomplete-profile case) - proposing
    to "add" a genuine gap would be fabrication.
The owner approves a proposal by hand via `update_profile_fact` (CLI `profile set`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from resumaker.config import get_settings
from resumaker.persistence import db, files, profile


@dataclass
class Proposal:
    requirement: str
    count: int
    companies: list[str] = field(default_factory=list)
    evidence: str = ""            # a profile bullet/skill backing it (supportedByResume only)


def _gap_items_for_tracked() -> list[tuple[str, dict]]:
    """(company, gap_item) across every tracked job that has a saved match report."""
    root = get_settings().output_root
    out: list[tuple[str, dict]] = []
    for e in db.list_tracker():
        if not e.run_id:
            continue
        report = root / e.run_id / "report.json"
        if not report.exists():
            continue
        data = files.read_json(report) or {}
        gap = (data.get("gap") or {})
        for item in gap.get("items", []) or []:
            out.append((e.company or e.title, item))
    return out


def _already_listed(requirement: str, skills: set[str]) -> bool:
    """A profile skill token appears verbatim in the requirement -> treat as already listed."""
    r = requirement.lower()
    return any(s.lower() in r for s in skills if len(s) >= 3)


def propose_from_tracker(limit: int = 25) -> dict[str, list[Proposal]]:
    """Aggregate gap items across tracked jobs into the two proposal buckets, ranked by how
    many tracked jobs each recurs in. Deduped case-insensitively by requirement text."""
    skills = profile.all_skills()
    buckets: dict[str, dict[str, Proposal]] = {"have_but_unlisted": {}, "recurring_gaps": {}}
    for company, item in _gap_items_for_tracked():
        status = item.get("status")
        req = (item.get("requirement") or "").strip()
        if not req:
            continue
        if status == "supportedByResume" and not _already_listed(req, skills):
            bucket = "have_but_unlisted"
        elif status == "gap":
            bucket = "recurring_gaps"
        else:
            continue
        key = req.lower()
        p = buckets[bucket].get(key)
        if p is None:
            p = Proposal(requirement=req, count=0, evidence=item.get("evidence", ""))
            buckets[bucket][key] = p
        p.count += 1
        if company and company not in p.companies:
            p.companies.append(company)

    def rank(d: dict[str, Proposal]) -> list[Proposal]:
        return sorted(d.values(), key=lambda p: (-p.count, p.requirement))[:limit]

    return {"have_but_unlisted": rank(buckets["have_but_unlisted"]),
            "recurring_gaps": rank(buckets["recurring_gaps"])}


# Counts of tracked reports actually available (so the CLI/API can say "based on N matches").
def tracked_report_count() -> int:
    root = get_settings().output_root
    return sum(1 for e in db.list_tracker() if e.run_id and (root / e.run_id / "report.json").exists())
