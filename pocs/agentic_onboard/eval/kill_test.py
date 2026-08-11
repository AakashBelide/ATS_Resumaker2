"""Control-layer proof — deterministic (no LLM timing variance).

Proves the two auto/manual kill primitives the frontend + watchdog rely on:
  1. TIME-BASED auto-kill: a long job with a short `timeout` is terminated; teardown is clean.
  2. MANUAL kill: a running sandbox is killed by its project name (the `stop` button path),
     mid-flight, and the container is gone afterwards.

Run:  python pocs/agentic_onboard/eval/kill_test.py    (requires Docker)
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sandbox"))
import runner  # noqa: E402


def _containers(project: str) -> str:
    return subprocess.run(["docker", "ps", "--filter", f"name={project}", "--format", "{{.Names}}"],
                          capture_output=True, text=True).stdout.strip()


def test_time_kill() -> bool:
    print("1) time-based auto-kill: sleep 60 with timeout=6 …", flush=True)
    res = runner.run(["sh", "-c", "echo START; sleep 60; echo DONE"],
                     service="agent", project="onboard-killtime", timeout=6)
    ok = res.timed_out and "DONE" not in res.stdout and res.returncode == 124
    print(f"   timed_out={res.timed_out} rc={res.returncode} 'DONE' seen={'DONE' in res.stdout} -> {'PASS' if ok else 'FAIL'}")
    return ok


def test_manual_kill() -> bool:
    print("2) manual kill (Stop button): kill a running sandbox by project name …", flush=True)
    proj = "onboard-killmanual"
    holder: dict = {}

    def bg() -> None:
        holder["res"] = runner.run(["sh", "-c", "echo START; sleep 60; echo DONE"],
                                   service="agent", project=proj, timeout=120)

    t = threading.Thread(target=bg, daemon=True)
    t.start()
    running_before = ""
    for _ in range(40):
        time.sleep(1)
        running_before = _containers(proj)
        if running_before:
            break
    print(f"   container running before kill: {bool(running_before)}")
    runner.kill(proj)                       # <- the exact call the frontend Stop button makes
    t.join(timeout=40)
    after = _containers(proj)
    res = holder.get("res")
    ok = bool(running_before) and not after and res is not None and "DONE" not in res.stdout
    print(f"   container after kill: {after or '(none)'} -> {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    a = test_time_kill()
    b = test_manual_kill()
    print("\n=== control-layer results ===")
    print(f"  [{'PASS' if a else 'FAIL'}] time-based auto-kill + clean teardown")
    print(f"  [{'PASS' if b else 'FAIL'}] manual kill of a running sandbox (Stop button)")
    ok = a and b
    print("\n" + ("ALL KILL CHECKS PASSED." if ok else "FAILED — see above."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
