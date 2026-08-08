"""Eval for Task 1.13 enrichment & preferences memory. Zero-LLM ($0).

Verifies (a) preferences load, (b) house-rule loading + prompt rendering +
add/replace round-trip, (c) enrichment log append + source-of-truth updater
round-trip with old->new capture. Mutations run against TEMP copies so the real
stores are never touched.

Run: `uv run python -m pocs.enrichment.eval`
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from core import profile as prof
from evals.harness import run_eval
from pocs import enrichment as enr


def build_cases():
    return [
        {"label": "preferences-loaded",
         "input": "prefs", "expect": "prefs"},
        {"label": "house-rules-nonempty-per-scope",
         "input": "rules", "expect": "rules"},
        {"label": "tailor-prompt-injects-key-rules",
         "input": "prompt", "expect": "prompt"},
        {"label": "do-not-repeat-present",
         "input": "dnr", "expect": "dnr"},
        {"label": "add-house-rule-roundtrip (temp)",
         "input": "add_rule", "expect": "add_rule"},
        {"label": "enrichment-log-append-roundtrip (temp)",
         "input": "log", "expect": "log"},
        {"label": "update-profile-fact-roundtrip (temp)",
         "input": "update", "expect": "update"},
    ]


def _run(kind):
    if kind == "prefs":
        return enr.preferences()
    if kind == "rules":
        return enr.house_rules_for("tailor", "skills", "render", "location", "fit")
    if kind == "prompt":
        return enr.house_rules_prompt(("tailor", "skills"))
    if kind == "dnr":
        return enr.do_not_repeat()
    if kind == "add_rule":
        d = Path(tempfile.mkdtemp())
        hr, lg = d / "hr.json", d / "log.jsonl"
        hr.write_text(json.dumps({"rules": [], "do_not_repeat": []}))
        enr.add_house_rule("tailor", "Test rule ABC", "because", rule_id="test-rule",
                           path=hr, log_path=lg)
        # replace-by-id must not duplicate
        enr.add_house_rule("tailor", "Test rule ABC v2", rule_id="test-rule",
                           path=hr, log_path=lg)
        data = json.loads(hr.read_text())
        return {"n_rules": len(data["rules"]),
                "text": data["rules"][0]["rule"],
                "logged": len(enr.read_enrichment_log(lg))}
    if kind == "log":
        d = Path(tempfile.mkdtemp())
        lg = d / "log.jsonl"
        enr.record_enrichment("test", "hello", log_path=lg, extra_field=1)
        enr.record_enrichment("test2", "world", log_path=lg)
        recs = enr.read_enrichment_log(lg)
        return {"count": len(recs), "first_kind": recs[0]["kind"],
                "has_extra": recs[0].get("extra_field") == 1}
    if kind == "update":
        d = Path(tempfile.mkdtemp())
        pf, lg = d / "profile.json", d / "log.jsonl"
        shutil.copy(prof.PROFILE_PATH, pf)
        rec = enr.update_profile_fact(
            ["contact", "location"], "Austin, TX", "test relocation",
            profile_path=pf, log_path=lg)
        after = json.loads(pf.read_text())["contact"]["location"]
        return {"new": after, "logged_old": rec["old"], "logged_new": rec["new"],
                "log_rows": len(enr.read_enrichment_log(lg))}
    raise ValueError(kind)


def _score(out, kind):
    if kind == "prefs":
        ok = (out.get("location", {}).get("base") == "Boston, MA"
              and "AI Engineer" in out.get("target_roles", [])
              and out.get("sponsorship", {}).get("needs_sponsorship_future") is True)
        return ok, f"base={out.get('location',{}).get('base')} roles={len(out.get('target_roles',[]))}"
    if kind == "rules":
        ids = {r["id"] for r in out}
        need = {"skills-completeness", "always-surface-genai", "relevance-first-bullets",
                "link-all-projects", "location-honest"}
        ok = need.issubset(ids)
        return ok, f"{len(out)} rules; missing={need - ids or 'none'}"
    if kind == "prompt":
        ok = ("HOUSE RULES" in out and "Docker" in out and "DO NOT REPEAT" in out
              and "GPT-4o" in out)
        return ok, f"len={len(out)} has_docker={'Docker' in out} has_dnr={'DO NOT REPEAT' in out}"
    if kind == "dnr":
        ok = len(out) >= 4 and any("skills" in d.lower() for d in out)
        return ok, f"{len(out)} do-not-repeat items"
    if kind == "add_rule":
        ok = out["n_rules"] == 1 and out["text"].endswith("v2") and out["logged"] == 2
        return ok, str(out)
    if kind == "log":
        ok = out["count"] == 2 and out["first_kind"] == "test" and out["has_extra"]
        return ok, str(out)
    if kind == "update":
        ok = (out["new"] == "Austin, TX" and out["logged_old"] == "Boston, MA"
              and out["logged_new"] == "Austin, TX" and out["log_rows"] == 1)
        return ok, str(out)
    return False, "unknown"


if __name__ == "__main__":
    print("STORE:", enr.summary())
    run_eval("enrichment", build_cases(), _run, _score)
