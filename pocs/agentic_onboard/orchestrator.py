"""Async onboarding orchestrator (POC of the human-in-the-loop model).

Flow per run:
  deterministic-first (fast, $0, zero injection surface) -> if it misses, the sandboxed
  agent fallback -> if the agent can't proceed without a human answer, it PAUSES in a
  `needs_input` state (question persisted) until `provide_input()` resumes it.

Progress is written exactly like the main app's ProgressReporter: a `status.json` snapshot +
an append-only `events.jsonl`, in the run dir, so a frontend can poll and pop a dialog when
`status == needs_input`. This mirrors the pattern in src/resumaker/pipeline/progress.py so the
later integration is a lift, not a rewrite. NO changes are made to the live app or DB here.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

POC_DIR = Path(__file__).resolve().parent
RUNS_DIR = POC_DIR / "runs"
sys.path.insert(0, str(POC_DIR / "sandbox"))
sys.path.insert(0, str(POC_DIR / "agent" / "tools"))
sys.path.insert(0, str(POC_DIR / "agent"))

import ats_probe  # noqa: E402  (host-side re-validation of the agent's board ref)
import resolve as agent_resolve  # noqa: E402
import runner  # noqa: E402  (for manual stop / kill)

# Defaults for the control layer (all overridable per run). Raised ceilings for now so runs
# aren't cut short while we iterate — tighten later once behavior is well-characterized.
MAX_TURNS = 60        # usage cap: bounds the agent's tool-call loop
TIME_LIMIT_S = 2400   # time-based auto-kill (40 min)
BUDGET_USD = 5.00     # usage cap: refuse to (re)start the agent past this cumulative cost


# ---------------------------------------------------------------- progress
@dataclass
class StageEvent:
    stage: str
    status: str            # start | done | skip | error | needs_input
    detail: str = ""
    ts: float = field(default_factory=time.time)


class RunLog:
    """status.json snapshot + events.jsonl append log — mirrors ProgressReporter."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.project = f"onboard-{run_id}"      # Compose project -> killable by name
        self.dir = RUNS_DIR / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events: list[StageEvent] = []
        self.state = "running"
        self.result: dict | None = None
        self.question: str | None = None
        self.cost_usd = 0.0
        self.turns = 0
        # resume/stop: carry forward prior history + usage so the timeline and budget persist
        sp = self.dir / "status.json"
        if sp.exists():
            prev = json.loads(sp.read_text())
            self.events = [StageEvent(**{k: e[k] for k in ("stage", "status", "detail", "ts")})
                           for e in prev.get("events", [])]
            self.cost_usd = float(prev.get("cost_usd") or 0.0)
            self.turns = int(prev.get("turns") or 0)

    def add_usage(self, meta: dict) -> None:
        self.cost_usd += float(meta.get("cost_usd") or 0.0)
        self.turns += int(meta.get("turns") or 0)

    def emit(self, stage: str, status: str, detail: str = "") -> None:
        ev = StageEvent(stage, status, detail)
        self.events.append(ev)
        with (self.dir / "events.jsonl").open("a") as f:
            f.write(json.dumps(asdict(ev)) + "\n")
        self._snapshot()
        print(f"  [{status:>11}] {stage}: {detail}", flush=True)

    def _snapshot(self) -> None:
        snap = {
            "run_id": self.run_id, "project": self.project, "state": self.state,
            "updated": time.time(), "question": self.question, "result": self.result,
            "cost_usd": round(self.cost_usd, 4), "turns": self.turns,
            "current": self.events[-1].stage if self.events else None,
            "events": [asdict(e) for e in self.events],
        }
        (self.dir / "status.json").write_text(json.dumps(snap, indent=2))

    def finish(self, state: str, result: dict | None = None, question: str | None = None) -> None:
        self.state, self.result, self.question = state, result, question
        self._snapshot()


# ---------------------------------------------------------------- validation
def _validate(board: dict) -> dict:
    """Host-side re-verification of the agent's claim (the trust boundary) via the REAL adapter
    registry — so ANY of the ~25 supported platforms (greenhouse … oracle_cloud, icims, phenom,
    eightfold …) is validated authoritatively, with zero per-source code in the POC. The agent
    only has to identify the platform + params correctly; this is what makes it universal."""
    src = board.get("source", "")
    token = board.get("token", "")
    extra = {k: str(v) for k, v in (board.get("extra", {}) or {}).items()}
    try:
        from resumaker.providers.sources import get_source  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"registry import failed: {e}"}
    try:
        stubs = get_source(src).list_postings(token, **extra)
    except Exception as e:  # noqa: BLE001 - unknown source / bad params / fetch error
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    n = len(stubs)
    return {"ok": n > 0, "count": n, "sample": [s.title for s in stubs[:5]]}


# ---------------------------------------------------------------- deterministic
def _deterministic(name: str, careers_url: str | None) -> dict | None:
    """Reuse the existing (fast, $0) resolver. Returns a board dict or None on miss."""
    try:
        from resumaker.ingestion import onboard  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - POC may run without the package importable
        return None
    res = onboard.resolve(name, careers_url=careers_url)
    if res.resolved and res.boards:
        b = res.boards[0]
        return {"source": b.source, "token": b.token, "extra": dict(b.extra or {})}
    return None


# ---------------------------------------------------------------- entrypoint
def run_onboarding(name: str, careers_url: str | None = None, *,
                   run_id: str | None = None, use_agent: bool = True,
                   max_turns: int = MAX_TURNS, time_limit: int = TIME_LIMIT_S,
                   budget_usd: float = BUDGET_USD) -> dict:
    run_id = run_id or uuid.uuid4().hex[:12]
    log = RunLog(run_id)
    log.emit("start", "start", f"name={name!r} careers_url={careers_url or '-'}")

    # 1) deterministic-first
    log.emit("deterministic", "start", "slug-probe + careers-page parse")
    board = _deterministic(name, careers_url)
    if board:
        v = _validate(board)
        if v.get("ok"):
            log.emit("deterministic", "done", f"{board['source']}:{board['token']} ({v['count']} jobs)")
            result = {"method": "deterministic", "board": board, "evidence": v}
            log.finish("resolved", result)
            return {"run_id": run_id, "state": "resolved", **result}
    log.emit("deterministic", "skip", "no confident board; escalating to agent")

    if not use_agent:
        log.finish("unresolved", {"note": "deterministic miss; agent disabled"})
        return {"run_id": run_id, "state": "unresolved"}

    # 2) agent fallback (sandboxed)
    return _run_agent(log, name, careers_url,
                      max_turns=max_turns, time_limit=time_limit, budget_usd=budget_usd)


def _run_agent(log: RunLog, name: str, careers_url: str | None, *,
               max_turns: int = MAX_TURNS, time_limit: int = TIME_LIMIT_S,
               budget_usd: float = BUDGET_USD) -> dict:
    # usage cap across the whole onboarding (initial + any resumes)
    if log.cost_usd >= budget_usd:
        log.emit("agent", "skip", f"budget ${budget_usd} reached (spent ${log.cost_usd:.4f})")
        log.finish("stopped", {"note": "usage budget reached"})
        return {"run_id": log.run_id, "state": "stopped", "note": "usage budget reached"}

    log.emit("agent", "start", f"sandboxed Claude resolver (max_turns={max_turns}, "
                               f"time_limit={time_limit}s, budget=${budget_usd})")
    try:
        contract = agent_resolve.resolve_via_agent(
            name, careers_url, project=log.project, max_turns=max_turns, time_limit=time_limit)
    except agent_resolve.AuthMissing as e:
        log.emit("agent", "error", str(e))
        log.finish("error", {"note": str(e)})
        return {"run_id": log.run_id, "state": "error", "note": str(e)}

    meta = contract.get("_meta", {})
    log.add_usage(meta)
    cost = meta.get("cost_usd")
    if cost is not None or meta.get("turns") is not None:
        log.emit("agent", "start", f"usage: ${log.cost_usd:.4f} cumulative, {log.turns} turns")

    status = contract.get("status")
    if status == "killed":   # time-based auto-kill fired inside the runner
        log.emit("agent", "error", contract.get("reason", "killed"))
        log.finish("killed", {"note": contract.get("reason", "killed")})
        return {"run_id": log.run_id, "state": "killed", "note": contract.get("reason")}

    if status == "resolved":
        board = contract.get("board", {})
        v = _validate(board)
        if v.get("ok"):
            log.emit("agent", "done", f"{board.get('source')}:{board.get('token')} ({v['count']} jobs)")
            result = {"method": "agent", "board": board, "evidence": v,
                      "agent_evidence": contract.get("evidence")}
            log.finish("resolved", result)
            return {"run_id": log.run_id, "state": "resolved", **result}
        log.emit("agent", "error", f"agent board failed host re-validation: {v}")
        log.finish("unresolved", {"note": "agent board did not validate", "board": board})
        return {"run_id": log.run_id, "state": "unresolved"}

    if status == "needs_input":
        q = contract.get("question", "Provide the careers URL or ATS board token.")
        log.emit("agent", "needs_input", q)
        log.finish("needs_input", question=q)
        return {"run_id": log.run_id, "state": "needs_input", "question": q,
                "tried": contract.get("tried")}

    log.emit("agent", "done", f"unresolved: {contract.get('note', '')}")
    log.finish("unresolved", {"note": contract.get("note", ""), "tried": contract.get("tried")})
    return {"run_id": log.run_id, "state": "unresolved", "note": contract.get("note", "")}


def provide_input(run_id: str, answer: str) -> dict:
    """Resume a `needs_input` run with the human's answer (treated as the careers URL / token
    hint). Re-invokes the agent with the answer supplied."""
    status_path = RUNS_DIR / run_id / "status.json"
    if not status_path.exists():
        raise FileNotFoundError(f"no such run: {run_id}")
    prev = json.loads(status_path.read_text())
    name = ""
    for e in prev.get("events", []):
        if e["stage"] == "start" and "name=" in e["detail"]:
            name = e["detail"].split("name=", 1)[1].split(" ")[0].strip("'\"")
            break
    log = RunLog(run_id)   # loads prior events + cumulative usage
    log.emit("resume", "start", f"human answer: {answer[:80]}")
    # Simplest resume model: treat the answer as the careers URL / board hint.
    careers = answer if ("http" in answer or "." in answer) else None
    return _run_agent(log, name or prev.get("name", ""), careers)


def stop(run_id: str) -> dict:
    """Manual kill — the frontend "Stop" button. Terminates the sandbox for this run (by its
    Compose project name) and marks the run stopped. Safe if the run already finished."""
    runner.kill(f"onboard-{run_id}")
    sp = RUNS_DIR / run_id / "status.json"
    if sp.exists():
        log = RunLog(run_id)
        log.emit("stop", "done", "manual kill: sandbox terminated by user")
        log.finish("stopped", {"note": "manually stopped by user"})
    return {"run_id": run_id, "state": "stopped"}
