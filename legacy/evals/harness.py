"""Minimal eval harness.

Each POC ships a small eval that calls `run_eval(...)` with:
  - cases:  list of dicts (fixtures) each with an "input" and optional "expect"
  - fn:     callable(input) -> output
  - scorer: callable(output, expect) -> (passed: bool, detail: str)

Prints a pass/fail table + summary. Keep POCs honest and regression-safe.
"""
from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from typing import Any

Case = dict[str, Any]


def run_eval(name: str, cases: list[Case],
             fn: Callable[[Any], Any],
             scorer: Callable[[Any, Any], tuple[bool, str]]) -> bool:
    print(f"\n=== EVAL: {name} ({len(cases)} cases) ===")
    passed = 0
    for i, case in enumerate(cases, 1):
        label = case.get("label", f"case-{i}")
        try:
            t0 = time.time()
            out = fn(case["input"])
            dt = time.time() - t0
            ok, detail = scorer(out, case.get("expect"))
        except Exception as e:  # noqa: BLE001
            ok, detail, dt = False, f"EXC {type(e).__name__}: {e}", 0.0
            traceback.print_exc()
        passed += int(ok)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}  ({dt:.1f}s)  {detail}")
    total = len(cases)
    print(f"--- {name}: {passed}/{total} passed ---")
    return passed == total
