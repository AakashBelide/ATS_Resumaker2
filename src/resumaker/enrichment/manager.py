"""Enrichment & preferences memory (Task 1.13).

A persistent memory/enrichment layer (career-ops `_profile.md`/`_custom.md`
parallel) that the pipeline reads every run and can update from conversation:

  (a) PREFERENCES  - job-search prefs (roles/comp/location/work-model/sponsorship),
      read by role-fit, apply-decision, location, tailoring. Lives in
      data/profile/preferences.json (see core.profile.load_preferences).
  (b) HOUSE RULES  - learned corrections applied every run (injected into the
      relevant stage's prompt), plus explicit "do-not-repeat" past mistakes.
      data/profile/house_rules.json.
  (c) ENRICHMENT   - an append-only audit log + a source-of-truth updater that
      folds new facts/corrections into the canonical profile.json and records
      what changed (and why), so nothing silently drifts.

Files are canonical; everything here is plain JSON so it is git-diffable and
human-editable (blueprint 5/16). No LLM here -> $0.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from resumaker.config import get_settings
from resumaker.persistence import profile as prof

HOUSE_RULES_PATH = get_settings().house_rules_path
ENRICH_LOG_PATH = get_settings().enrichment_log_path

# Which house-rule scopes each pipeline stage should honor.
STAGE_SCOPES = {
    "tailor": ("tailor", "skills"),
    "render": ("render",),
    "location": ("location",),
    "fit": ("fit",),
    "apply": ("fit", "apply"),
}


def _now() -> str:
    return _dt.date.today().isoformat()


# ---------------------------------------------------------------- house rules
def load_house_rules(path: Path | None = None) -> dict:
    _default = {"rules": [], "do_not_repeat": []}
    if path is not None:                          # explicit path -> read that file (tests/tools)
        return json.loads(path.read_text()) if path.exists() else _default
    # DB-backed (dual-mode), auto-migrating the legacy JSON file on first read
    from resumaker.persistence.profile import _load_doc
    return _load_doc("house_rules", get_settings().house_rules_path, default=_default)


def house_rules_for(*scopes: str, path: Path | None = None) -> list[dict]:
    """Return rules whose scope is in `scopes` (scope 'global' always included)."""
    wanted = set(scopes) | {"global"}
    return [r for r in load_house_rules(path).get("rules", [])
            if r.get("scope") in wanted]


def do_not_repeat(path: Path | None = None) -> list[str]:
    return [d["item"] for d in load_house_rules(path).get("do_not_repeat", [])
            if d.get("item")]


def house_rules_prompt(scopes: tuple[str, ...] = ("tailor", "skills"),
                       path: Path | None = None) -> str:
    """Render the learned rules (+ do-not-repeat) as a prompt block to append to
    a stage prompt. Empty string if there are none (so it is safe to always add)."""
    rules = house_rules_for(*scopes, path=path)
    dnr = do_not_repeat(path)
    if not rules and not dnr:
        return ""
    lines = ["\n\nLEARNED HOUSE RULES (owner corrections - APPLY THESE, they override defaults on conflict):"]
    for r in rules:
        lines.append(f"- {r['rule']}")
    if dnr:
        lines.append("DO NOT REPEAT these past mistakes:")
        lines += [f"- {d}" for d in dnr]
    return "\n".join(lines)


def add_house_rule(scope: str, rule: str, rationale: str = "",
                   rule_id: str | None = None, path: Path | None = None,
                   log_path: Path | None = None) -> dict:
    """Add/replace a house rule (by id) and log it."""
    path = path or HOUSE_RULES_PATH
    data = load_house_rules(path)
    entry = {"id": rule_id or rule[:32].strip().lower().replace(" ", "-"),
             "scope": scope, "rule": rule, "rationale": rationale, "added": _now()}
    data.setdefault("rules", [])
    data["rules"] = [r for r in data["rules"] if r.get("id") != entry["id"]]
    data["rules"].append(entry)
    data.setdefault("_meta", {})["updated"] = _now()
    path.write_text(json.dumps(data, indent=2))
    record_enrichment("house_rule_added", f"[{scope}] {rule}",
                      log_path=log_path, rule_id=entry["id"])
    return entry


def add_do_not_repeat(item: str, path: Path | None = None,
                      log_path: Path | None = None) -> dict:
    path = path or HOUSE_RULES_PATH
    data = load_house_rules(path)
    entry = {"item": item, "added": _now()}
    data.setdefault("do_not_repeat", [])
    if item not in [d.get("item") for d in data["do_not_repeat"]]:
        data["do_not_repeat"].append(entry)
        data.setdefault("_meta", {})["updated"] = _now()
        path.write_text(json.dumps(data, indent=2))
        record_enrichment("do_not_repeat_added", item, log_path=log_path)
    return entry


# ---------------------------------------------------------------- enrichment log
def record_enrichment(kind: str, detail: str, *, source: str = "conversation",
                      log_path: Path | None = None, **extra: Any) -> dict:
    """Append one audit record (append-only JSONL)."""
    log_path = log_path or ENRICH_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"),
           "kind": kind, "detail": detail, "source": source, **extra}
    with log_path.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def read_enrichment_log(log_path: Path | None = None) -> list[dict]:
    log_path = log_path or ENRICH_LOG_PATH
    if not log_path.exists():
        return []
    return [json.loads(ln) for ln in log_path.read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------- source-of-truth updater
def _set_by_path(obj: Any, path: list, value: Any) -> Any:
    """Set a nested value by a path of dict keys / list indices. Returns old value."""
    cur = obj
    for step in path[:-1]:
        cur = cur[step]
    last = path[-1]
    old = cur[last] if (isinstance(cur, list) or last in cur) else None
    cur[last] = value
    return old


def update_profile_fact(path: list, value: Any, reason: str, *,
                        source: str = "conversation",
                        profile_path: Path | None = None,
                        log_path: Path | None = None) -> dict:
    """Fold a new/corrected fact into the canonical profile.json, log the change
    (old -> new + reason), and invalidate the profile cache. `path` is a list of
    dict keys / list indices, e.g. ['contact','location'] or ['projects',1,'url'].
    NEVER call this to fabricate - only to record real owner-provided facts."""
    profile_path = profile_path or get_settings().profile_path
    data = json.loads(profile_path.read_text())
    old = _set_by_path(data, path, value)
    data.setdefault("_meta", {})["updated"] = _now()
    profile_path.write_text(json.dumps(data, indent=1))
    prof.invalidate()
    return record_enrichment(
        "profile_update", reason, source=source, log_path=log_path,
        field=".".join(str(p) for p in path), old=old, new=value)


# ---------------------------------------------------------------- convenience
def preferences() -> dict:
    return prof.load_preferences()


def summary() -> str:
    prefs = preferences()
    hr = load_house_rules()
    return (f"preferences: {len(prefs)} keys (target_roles="
            f"{len(prefs.get('target_roles', []))}, location="
            f"{prefs.get('location', {}).get('base', '?')})  |  "
            f"house_rules: {len(hr.get('rules', []))} rules, "
            f"{len(hr.get('do_not_repeat', []))} do-not-repeat  |  "
            f"enrichment_log: {len(read_enrichment_log())} records")
