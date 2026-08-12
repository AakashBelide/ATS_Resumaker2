"""In-process background run worker.

A single-user tool doesn't need Celery/Redis: a small ThreadPoolExecutor runs the
(2-5 min, sync) pipeline off the request thread, and a per-run thread-safe queue carries
progress events to the SSE endpoint. Run metadata is persisted by the orchestrator to
SQLite, so status survives restarts even though the live event stream does not.
"""
from __future__ import annotations

import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from resumaker.domain import PipelineResult
from resumaker.observability.logging import get_logger
from resumaker.pipeline import run_pipeline

_log = get_logger("resumaker.api.worker")
_END = {"stage": "__end__", "status": "done", "detail": ""}


@dataclass
class RunHandle:
    run_id: str
    url: str
    events: queue.Queue = field(default_factory=queue.Queue)
    result: PipelineResult | None = None
    finished: bool = False


class RunManager:
    """Owns the executor and live run handles. One instance per process."""

    def __init__(self, max_workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="run")
        self._runs: dict[str, RunHandle] = {}

    def start(self, url: str, **options) -> str:
        """Mint a run id and execute it in-process. Convenience wrapper over `submit`."""
        run_id = uuid.uuid4().hex[:12]
        self.submit(run_id, url, **options)
        return run_id

    def submit(self, run_id: str, url: str, **options) -> None:
        """Execute a pipeline run in-process under the given run id (the InProcessQueue path).
        The id is supplied by the caller so it matches the DB/artifacts and any queue payload."""
        handle = RunHandle(run_id=run_id, url=url)
        self._runs[run_id] = handle

        def on_progress(stage: str, status: str, detail: str = "") -> None:
            handle.events.put({"stage": stage, "status": status, "detail": detail})

        def task() -> None:
            try:
                handle.result = run_pipeline(url, run_id=run_id, on_progress=on_progress,
                                             **options)
            except Exception as e:  # noqa: BLE001 - surfaced to the client via the stream
                _log.warning("run crashed", extra={"run_id": run_id, "error": str(e)})
                handle.events.put({"stage": "pipeline", "status": "error", "detail": str(e)})
            finally:
                handle.finished = True
                handle.events.put(dict(_END))

        self._pool.submit(task)
        _log.info("run started", extra={"run_id": run_id, "url": url})

    def submit_background(self, fn, *args) -> None:
        """Run an arbitrary callable off the request thread (e.g. a tracker match locally). The
        cloud path enqueues to the worker instead; this keeps the same fire-and-forget shape."""
        self._pool.submit(fn, *args)

    def handle(self, run_id: str) -> RunHandle | None:
        return self._runs.get(run_id)


# Process-wide singleton (created by the app factory).
manager = RunManager()
