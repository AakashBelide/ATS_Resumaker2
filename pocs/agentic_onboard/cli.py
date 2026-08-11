"""POC CLI for agentic auto-onboarding.

  python -m pocs.agentic_onboard.cli resolve "State Street" [--careers-url https://careers.x.com]
  python -m pocs.agentic_onboard.cli provide-input <run_id> "https://careers.x.com/jobs"
  python -m pocs.agentic_onboard.cli watch <run_id>
  python -m pocs.agentic_onboard.cli containment      # run the Phase-A security proof

Run from the repo root (so `resumaker` is importable for the deterministic-first step):
  uv run python -m pocs.agentic_onboard.cli resolve "Ramp"
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

POC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(POC_DIR))
sys.path.insert(0, str(POC_DIR / "eval"))

import orchestrator  # noqa: E402


def _watch(run_id: str) -> int:
    status = POC_DIR / "runs" / run_id / "status.json"
    seen = 0
    for _ in range(600):
        if status.exists():
            snap = json.loads(status.read_text())
            evs = snap.get("events", [])
            for e in evs[seen:]:
                print(f"  [{e['status']:>11}] {e['stage']}: {e['detail']}")
            seen = len(evs)
            if snap.get("state") not in ("running", None):
                print(f"\nstate = {snap['state']}")
                if snap.get("question"):
                    print(f"question = {snap['question']}")
                return 0
        time.sleep(0.5)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="agentic_onboard")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("resolve", help="resolve a company -> ATS board (deterministic, then agent)")
    r.add_argument("name")
    r.add_argument("--careers-url", default=None)
    r.add_argument("--no-agent", action="store_true", help="deterministic only")
    r.add_argument("--max-turns", type=int, default=orchestrator.MAX_TURNS, help="usage cap: agent tool-call loop")
    r.add_argument("--time-limit", type=int, default=orchestrator.TIME_LIMIT_S, help="wall-clock auto-kill (s)")
    r.add_argument("--budget", type=float, default=orchestrator.BUDGET_USD, help="usage cap: max cumulative $")

    p = sub.add_parser("provide-input", help="resume a needs_input run with a human answer")
    p.add_argument("run_id")
    p.add_argument("answer")

    w = sub.add_parser("watch", help="tail a run's progress")
    w.add_argument("run_id")

    s = sub.add_parser("stop", help="manual kill: terminate a running onboarding sandbox")
    s.add_argument("run_id")

    sub.add_parser("containment", help="run the Phase-A sandbox containment proof")

    a = ap.parse_args()

    if a.cmd == "resolve":
        out = orchestrator.run_onboarding(a.name, a.careers_url, use_agent=not a.no_agent,
                                          max_turns=a.max_turns, time_limit=a.time_limit,
                                          budget_usd=a.budget)
    elif a.cmd == "provide-input":
        out = orchestrator.provide_input(a.run_id, a.answer)
    elif a.cmd == "stop":
        out = orchestrator.stop(a.run_id)
    elif a.cmd == "watch":
        return _watch(a.run_id)
    elif a.cmd == "containment":
        import containment_test  # noqa: PLC0415
        return containment_test.main()
    else:  # pragma: no cover
        ap.error("unknown command")

    print("\n" + json.dumps(out, indent=2))
    return 0 if out.get("state") in ("resolved", "needs_input") else 1


if __name__ == "__main__":
    raise SystemExit(main())
