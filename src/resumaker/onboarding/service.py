"""Agentic onboarding service (Phase C).

Async lifecycle over the `onboarding_runs` table (the source of truth — runs survive restarts and
the frontend polls them, popping a dialog when `state == needs_input`). Flow: deterministic-first
($0, no sandbox) -> sandboxed agent fallback -> `needs_input` pause -> resume with a human answer.

Local-first: an in-process ThreadPoolExecutor runs the work off the request thread. The cloud path
swaps this seam for Cloud Tasks -> a worker endpoint (same service code), per DEPLOYMENT.md.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from resumaker.domain import BoardRef, Company, OnboardEvent, OnboardingRun
from resumaker.observability.logging import get_logger
from resumaker.onboarding.agent import get_agent_runner
from resumaker.persistence import db

_log = get_logger("resumaker.onboarding.service")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="onboard")
_EXTERNAL_TERMINAL = ("stopped", "killed")


class _Cancelled(Exception):
    """Raised inside a background run when stop() has flipped the row to a terminal state, so the
    worker bails WITHOUT overwriting that state with its own (now stale) in-memory state."""


# ------------------------------------------------------------------ helpers
def _cancelled(run: OnboardingRun) -> bool:
    cur = db.get_onboarding_run(run.id)
    return bool(cur and cur.state in _EXTERNAL_TERMINAL and run.state not in _EXTERNAL_TERMINAL)


def _emit(run: OnboardingRun, stage: str, status: str, detail: str = "") -> None:
    # Cooperative cancellation: every state write goes through here, so an external stop() is
    # detected before we clobber it.
    if _cancelled(run):
        raise _Cancelled
    run.events.append(OnboardEvent(stage=stage, status=status, detail=detail, ts=time.time()))
    db.upsert_onboarding_run(run)
    _log.info("onboard %s [%s] %s: %s", run.id, status, stage, detail)


def _deterministic(name: str, careers_url: str | None) -> BoardRef | None:
    from resumaker.ingestion import onboard  # noqa: PLC0415
    res = onboard.resolve(name, careers_url=careers_url)
    return res.boards[0] if (res.resolved and res.boards) else None


def _validate(board: BoardRef) -> dict:
    """Host-side re-verification via the real adapter registry (trust boundary + any of ~25
    platforms). Deterministic hits are already probed, but re-validating is cheap and uniform."""
    from resumaker.providers.sources import get_source  # noqa: PLC0415
    try:
        extra = {k: str(v) for k, v in (board.extra or {}).items()}
        stubs = get_source(board.source).list_postings(board.token, **extra)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    n = len(stubs)
    return {"ok": n > 0, "count": n, "sample": [s.title for s in stubs[:5]]}


def _resolve_and_add(run: OnboardingRun, method: str, board: BoardRef, evidence: dict) -> None:
    if _cancelled(run):          # don't add to the watchlist if the user stopped it
        raise _Cancelled
    run.method, run.board, run.evidence, run.state = method, board, evidence, "resolved"
    db.add_company(Company(name=run.name, boards=[board]))
    _emit(run, method, "done",
          f"{board.source}:{board.token} ({evidence.get('count', '?')} jobs) — added to watchlist")


def _finish(run: OnboardingRun, state: str, note: str = "") -> None:
    run.state = state
    if state == "error":
        run.error = note
    _emit(run, "run" if state == "error" else "agent",
          "error" if state == "error" else "done", f"{state}: {note}" if note else state)


def _apply_agent_contract(run: OnboardingRun, contract: dict) -> None:
    run.cost_usd += float(contract.get("cost_usd") or 0.0)
    run.turns += int(contract.get("turns") or 0)
    # respect an external stop that landed while the agent ran
    cur = db.get_onboarding_run(run.id)
    if cur and cur.state in ("stopped", "killed"):
        return
    status = contract.get("status")
    if status == "resolved" and contract.get("board"):
        board = BoardRef(**contract["board"])
        v = _validate(board)
        if v.get("ok"):
            _resolve_and_add(run, "agent", board, v)
        else:
            _finish(run, "unresolved",
                    note=f"agent board failed re-validation: {v.get('error', 'no postings')}")
    elif status == "needs_input":
        run.question = contract.get("question") or "Provide the careers URL or an ATS board token."
        run.state = "needs_input"
        _emit(run, "agent", "needs_input", run.question)
    elif status == "killed":
        _finish(run, "killed", note=contract.get("note", "time/budget limit reached"))
    else:
        _finish(run, "unresolved", note=contract.get("note", "no board found"))


# ------------------------------------------------------------------ public API
def start(name: str, careers_url: str | None = None) -> OnboardingRun:
    """Create an onboarding run (state=running) and kick off the async resolve. Returns the run
    immediately (poll `get`/the API for progress)."""
    run = OnboardingRun(id=uuid.uuid4().hex[:12], name=name.strip(),
                        careers_url=(careers_url or "").strip(), state="running")
    _emit(run, "start", "start", f"name={run.name!r} careers_url={run.careers_url or '-'}")
    _pool.submit(_run, run.id)
    return run


def _run(run_id: str) -> None:
    run = db.get_onboarding_run(run_id)
    if run is None:
        return
    try:
        _emit(run, "deterministic", "start", "slug-probe + careers-page parse")
        board = _deterministic(run.name, run.careers_url or None)
        if board is not None:
            v = _validate(board)
            if v.get("ok"):
                _resolve_and_add(run, "deterministic", board, v)
                return
        _emit(run, "deterministic", "skip", "no confident board; escalating to agent")

        runner = get_agent_runner()
        contract = runner.resolve(run.name, run.careers_url or None, run_id=run_id,
                                  on_event=lambda st, sta, d="": _emit(run, st, sta, d))
        _apply_agent_contract(run, contract)
    except _Cancelled:
        _log.info("onboard run %s cancelled (stopped by user)", run_id)
    except Exception as e:  # noqa: BLE001
        _log.warning("onboard run %s crashed: %s", run_id, e)
        _finish(run, "error", note=str(e))


def provide_input(run_id: str, answer: str) -> OnboardingRun:
    """Resume a `needs_input` run with the human's answer (treated as the careers URL / board hint)."""
    run = db.get_onboarding_run(run_id)
    if run is None:
        raise KeyError(run_id)
    run.state, run.question = "running", ""
    _emit(run, "resume", "start", f"human answer: {answer[:80]}")
    careers = answer if ("http" in answer or "." in answer) else (run.careers_url or None)
    _pool.submit(_resume, run_id, careers)
    return run


def _resume(run_id: str, careers: str | None) -> None:
    run = db.get_onboarding_run(run_id)
    if run is None:
        return
    try:
        runner = get_agent_runner()
        contract = runner.resolve(run.name, careers, run_id=run_id,
                                  on_event=lambda st, sta, d="": _emit(run, st, sta, d))
        _apply_agent_contract(run, contract)
    except _Cancelled:
        _log.info("onboard resume %s cancelled (stopped by user)", run_id)
    except Exception as e:  # noqa: BLE001
        _finish(run, "error", note=str(e))


def stop(run_id: str) -> OnboardingRun | None:
    """Manual kill (frontend Stop button): terminate the sandbox for this run + mark it stopped."""
    run = db.get_onboarding_run(run_id)
    if run is None:
        return None
    get_agent_runner().stop(run_id)
    run.state = "stopped"
    _emit(run, "stop", "done", "stopped by user")
    return run


def get(run_id: str) -> OnboardingRun | None:
    return db.get_onboarding_run(run_id)


def list_runs(limit: int = 50) -> list[OnboardingRun]:
    return db.list_onboarding_runs(limit=limit)
