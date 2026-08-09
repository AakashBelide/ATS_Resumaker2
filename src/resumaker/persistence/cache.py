"""Content-addressed disk cache for expensive, deterministic results - primarily LLM
responses (keyed by provider+model+system+prompt+params) and scraped JDs.

Why disk, not Redis: a single-user tool makes a handful of calls; a JSON file per key
under `cache_dir` is zero-ops, survives restarts, and is inspectable. The biggest win
is skipping repeat LLM calls during re-runs/tests - real cost + latency saved for free.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from resumaker.config import get_settings


def _namespace_dir(namespace: str) -> Path:
    d = get_settings().cache_dir / namespace
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_key(*parts: Any) -> str:
    """Stable sha256 over the parts (dicts are JSON-normalized with sorted keys)."""
    h = hashlib.sha256()
    for p in parts:
        material = json.dumps(p, sort_keys=True, default=str) if not isinstance(p, str) else p
        h.update(material.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def get(namespace: str, key: str) -> Any | None:
    path = _namespace_dir(namespace) / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["value"]
    except (json.JSONDecodeError, KeyError):
        return None


def put(namespace: str, key: str, value: Any) -> None:
    path = _namespace_dir(namespace) / f"{key}.json"
    payload = {"ts": time.time(), "value": value}
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")


def enabled() -> bool:
    return get_settings().llm_cache_enabled
