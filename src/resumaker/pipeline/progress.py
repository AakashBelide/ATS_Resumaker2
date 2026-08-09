"""Progress reporting (Task 2.5).

One event stream, rendered many ways. The orchestrator emits stage events through a
ProgressReporter; the reporter (a) forwards to an optional in-process callback (the
CLI's live view) AND (b) persists to `status.json` (current snapshot) + `progress.jsonl`
(append-only log) in the run's out-dir. That makes even a detached/background run
observable - `resumaker watch <dir>` (or the future web UI over SSE) just reads those
files. Nothing here does any LLM/IO-heavy work; it's a thin, dependency-free sink.
"""
from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class StageEvent:
    stage: str
    status: str                 # start | done | skip | error
    detail: str = ""
    ts: float = 0.0
    elapsed: float | None = None


class ProgressReporter:
    def __init__(self, url: str = "",
                 on_event: Callable[[StageEvent], None] | None = None,
                 out_dir: str | None = None):
        self.url = url
        self.on_event = on_event
        self.events: list[StageEvent] = []
        self._starts: dict[str, float] = {}
        self.t0 = time.time()
        self.done = False
        self.out_dir: Path | None = None
        if out_dir:
            self.set_out_dir(out_dir)

    # -- output location (may be set once known, e.g. after structuring) --
    def set_out_dir(self, path: str) -> None:
        self.out_dir = Path(path)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # flush everything captured before the dir was known
        with (self.out_dir / "progress.jsonl").open("w") as fh:
            for e in self.events:
                fh.write(json.dumps(asdict(e)) + "\n")
        self._write_status()

    # -- emit an event --
    def emit(self, stage: str, status: str, detail: str = "") -> StageEvent:
        now = time.time()
        elapsed = None
        if status == "start":
            self._starts[stage] = now
        elif stage in self._starts:
            elapsed = round(now - self._starts[stage], 2)
        ev = StageEvent(stage, status, detail, round(now, 3), elapsed)
        self.events.append(ev)
        if self.on_event:
            # a broken renderer must not kill the run
            with contextlib.suppress(Exception):
                self.on_event(ev)
        if self.out_dir:
            with (self.out_dir / "progress.jsonl").open("a") as fh:
                fh.write(json.dumps(asdict(ev)) + "\n")
            self._write_status()
        return ev

    def finish(self) -> None:
        self.done = True
        if self.out_dir:
            self._write_status()

    # -- current state (what watchers render) --
    def snapshot(self) -> dict:
        stages: dict[str, dict] = {}
        order: list[str] = []
        for e in self.events:
            if e.stage not in stages:
                order.append(e.stage)
            stages[e.stage] = {"stage": e.stage, "status": e.status,
                               "detail": e.detail, "elapsed": e.elapsed}
        return {
            "url": self.url,
            "out_dir": str(self.out_dir) if self.out_dir else "",
            "updated": round(time.time(), 3),
            "elapsed": round(time.time() - self.t0, 2),
            "current": self.events[-1].stage if self.events else "",
            "done": self.done,
            "stages": [stages[s] for s in order],
        }

    def _write_status(self) -> None:
        if self.out_dir is None:  # only called when out_dir is set; guard for types
            return
        (self.out_dir / "status.json").write_text(json.dumps(self.snapshot(), indent=1))
