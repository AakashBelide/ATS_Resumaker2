"""Eval for Task 2.5 progress reporter + status files. Zero-LLM ($0).

Run: `uv run python -m evals.progress_eval`
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.progress import ProgressReporter
from evals.harness import run_eval


def build_cases():
    return [
        {"label": "emit-writes-status-and-jsonl", "input": "files", "expect": "files"},
        {"label": "snapshot-collapses-to-latest-per-stage", "input": "snap", "expect": "snap"},
        {"label": "set_out_dir-flushes-pre-dir-events", "input": "flush", "expect": "flush"},
        {"label": "callback-forwarded", "input": "cb", "expect": "cb"},
    ]


def _run(kind):
    if kind == "files":
        d = Path(tempfile.mkdtemp())
        r = ProgressReporter(url="u", out_dir=str(d))
        r.emit("scrape", "start"); r.emit("scrape", "done")
        r.finish()
        status = json.loads((d / "status.json").read_text())
        lines = [json.loads(x) for x in (d / "progress.jsonl").read_text().splitlines() if x]
        return {"status_done": status["done"], "n_stages": len(status["stages"]),
                "jsonl_rows": len(lines), "elapsed_set": lines[1]["elapsed"] is not None}
    if kind == "snap":
        r = ProgressReporter(url="u")
        r.emit("a", "start"); r.emit("a", "done"); r.emit("b", "start"); r.emit("b", "error", "boom")
        snap = r.snapshot()
        by = {s["stage"]: s for s in snap["stages"]}
        return {"stages": [s["stage"] for s in snap["stages"]],
                "a_status": by["a"]["status"], "b_status": by["b"]["status"],
                "b_detail": by["b"]["detail"]}
    if kind == "flush":
        d = Path(tempfile.mkdtemp())
        r = ProgressReporter(url="u")               # no out-dir yet
        r.emit("scrape", "start"); r.emit("scrape", "done")
        r.set_out_dir(str(d))                        # should flush both events
        rows = [x for x in (d / "progress.jsonl").read_text().splitlines() if x]
        return {"flushed_rows": len(rows), "status_exists": (d / "status.json").exists()}
    if kind == "cb":
        seen = []
        r = ProgressReporter(on_event=lambda ev: seen.append((ev.stage, ev.status)))
        r.emit("x", "start"); r.emit("x", "done")
        return seen
    raise ValueError(kind)


def _score(out, kind):
    if kind == "files":
        ok = (out["status_done"] and out["n_stages"] == 1 and out["jsonl_rows"] == 2
              and out["elapsed_set"])
        return ok, str(out)
    if kind == "snap":
        ok = (out["stages"] == ["a", "b"] and out["a_status"] == "done"
              and out["b_status"] == "error" and out["b_detail"] == "boom")
        return ok, str(out)
    if kind == "flush":
        ok = out["flushed_rows"] == 2 and out["status_exists"]
        return ok, str(out)
    if kind == "cb":
        ok = out == [("x", "start"), ("x", "done")]
        return ok, str(out)
    return False, "unknown"


if __name__ == "__main__":
    run_eval("progress", build_cases(), _run, _score)
