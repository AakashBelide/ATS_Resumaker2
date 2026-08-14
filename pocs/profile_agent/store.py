"""Run-state persistence for the profile agent.

One run == one conversation. State lives in `runs/<id>/status.json` (CLI POC); the shape mirrors
the onboarding service so an API/DB seam can drop in later without changing callers. Everything is
plain JSON so `watch` can tail it and the web can poll it.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Mode = Literal["intake", "enhance", "gapchat"]
State = Literal["running", "needs_input", "done", "stopped", "error"]

RUNS_DIR = Path(__file__).parent / "runs"


@dataclass
class Event:
    stage: str
    status: str
    detail: str = ""
    ts: float = field(default_factory=time.time)


@dataclass
class Proposal:
    """A single proposed profile write. `source_quote` MUST be a verbatim span of the user's own
    message (or the uploaded resume for intake) - the anti-fabrication check rejects any proposal
    without one before it is ever shown to the user."""
    kind: str            # add_skill | add_metric | add_bullet | edit_summary | add_project | set_pref | add_house_rule | add_equivalence
    path: list           # nested key path into profile.json (or a pseudo-path for prefs/house rules)
    value: Any
    source_quote: str    # verbatim span of the user's input that justifies this write
    preview: str = ""    # human-readable one-liner shown at confirm time
    confidence: float = 0.0


@dataclass
class Applied:
    """An applied write, kept so `/undo` can revert it to its prior value."""
    kind: str
    path: list
    old_value: Any
    new_value: Any
    detail: str = ""


@dataclass
class RunState:
    run_id: str
    mode: Mode
    state: State = "running"
    events: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)      # [{role: user|agent, text}]
    pending: list[dict] = field(default_factory=list)       # Proposal dicts awaiting confirm
    applied: list[dict] = field(default_factory=list)       # Applied dicts (for /undo)
    meta: dict = field(default_factory=dict)                # report_run_id, turns_used, started_at, cost_usd, etc.

    # -- convenience ------------------------------------------------------
    def add_event(self, stage: str, status: str, detail: str = "") -> None:
        self.events.append(asdict(Event(stage, status, detail)))

    def add_turn(self, role: str, text: str) -> None:
        self.history.append({"role": role, "text": text})


def runs_dir() -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR


def new_run(mode: Mode, **meta: Any) -> RunState:
    run_id = f"{mode}-{uuid.uuid4().hex[:8]}"
    st = RunState(run_id=run_id, mode=mode, meta={"started_at": time.time(), "turns_used": 0,
                                                  "cost_usd": 0.0, **meta})
    st.add_event("start", "ok", f"{mode} run created")
    save(st)
    return st


def _path(run_id: str) -> Path:
    return runs_dir() / run_id / "status.json"


def save(st: RunState) -> None:
    p = _path(st.run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(st), indent=2, default=str))


def load(run_id: str) -> RunState:
    data = json.loads(_path(run_id).read_text())
    return RunState(**data)


def exists(run_id: str) -> bool:
    return _path(run_id).exists()
