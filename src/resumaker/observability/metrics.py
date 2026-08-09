"""Minimal in-process metrics registry with Prometheus text exposition.

Deliberately dependency-free (no prometheus_client): a single-user tool doesn't need
a client library, and the exposition format is trivial. The API's `/metrics` route
calls `render()`; scrape it with Grafana Cloud's free tier if you want dashboards.

Counters are monotonic; gauges are set-and-read. Labels are a small dict. Thread-safe.
"""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}


def _key(name: str, labels: dict[str, str] | None):
    return name, tuple(sorted((labels or {}).items()))


def inc(name: str, value: float = 1.0, **labels: str) -> None:
    with _lock:
        _counters[_key(name, labels)] += value


def set_gauge(name: str, value: float, **labels: str) -> None:
    with _lock:
        _gauges[_key(name, labels)] = value


def _fmt_labels(label_pairs: tuple[tuple[str, str], ...]) -> str:
    if not label_pairs:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in label_pairs)
    return "{" + inner + "}"


def render() -> str:
    """Prometheus text exposition of all counters + gauges."""
    lines: list[str] = []
    with _lock:
        for (name, labels), val in sorted(_counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{_fmt_labels(labels)} {val}")
        for (name, labels), val in sorted(_gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{_fmt_labels(labels)} {val}")
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Test helper: clear all metrics."""
    with _lock:
        _counters.clear()
        _gauges.clear()
