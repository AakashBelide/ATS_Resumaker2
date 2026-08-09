"""Notifications for newly-ingested postings (RI.4).

Always writes a durable digest line (JSONL under the output dir) and structured-logs a
summary; if `notify_webhook` is configured, POSTs the digest there too. Human decides what
to act on - nothing auto-applies (blueprint §21)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from resumaker.config import get_settings
from resumaker.domain import JobRecord
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.ingestion.notify")


def notify_new(jobs: list[JobRecord]) -> None:
    if not jobs:
        return
    digest = {
        "ts": datetime.now(UTC).isoformat(),
        "count": len(jobs),
        "jobs": [{"company": j.company, "title": j.title, "url": j.url,
                  "location": j.location} for j in jobs],
    }
    s = get_settings()
    path = s.output_root / "_watchlist_digest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(digest) + "\n")
    _log.info("new postings", extra={"count": len(jobs)})

    if s.notify_webhook:
        try:
            import httpx
            httpx.post(s.notify_webhook, json=digest, timeout=10)
        except Exception as e:  # noqa: BLE001 - notification best-effort
            _log.warning("webhook notify failed", extra={"error": str(e)})
