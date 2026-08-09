"""The uniform stage contract.

Every pipeline stage is a plain callable over the domain models in `resumaker.domain`
(JobPosting in, KeywordSet/GapReport/ResumeDoc/... out). Rather than force each into a
class, the orchestrator wraps each call with `run_stage`, which is the single place that
handles timing, progress emission, metrics, and error propagation - so all stages behave
uniformly and observably without ceremony in the stage code itself.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from resumaker.observability import metrics
from resumaker.observability.logging import get_logger
from resumaker.pipeline.progress import ProgressReporter

_log = get_logger("resumaker.pipeline")


def run_stage[T](reporter: ProgressReporter, name: str, fn: Callable[[], T],
                 timings: dict[str, float]) -> T:
    """Run one stage: emit start/done (or error), record elapsed + a metrics counter,
    and structured-log the transition. Re-raises so the orchestrator decides fatality."""
    reporter.emit(name, "start")
    t0 = time.time()
    try:
        out = fn()
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        timings[name] = elapsed
        metrics.inc("resumaker_stage_total", stage=name, status="error")
        reporter.emit(name, "error", str(e))
        _log.warning("stage error", extra={"stage": name, "elapsed": elapsed,
                                           "error": f"{type(e).__name__}: {e}"})
        raise
    elapsed = round(time.time() - t0, 2)
    timings[name] = elapsed
    metrics.inc("resumaker_stage_total", stage=name, status="done")
    reporter.emit(name, "done")
    _log.info("stage done", extra={"stage": name, "elapsed": elapsed})
    return out
