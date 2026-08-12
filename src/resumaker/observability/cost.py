"""Cost guard: tracks LLM spend and enforces a hard cap on paid Gemini API usage.

Claude CLI usage is logged (visibility into subscription burn) but does NOT count
against the Gemini budget, since it draws on the owner's Claude subscription rather
than paid API tokens. Anthropic API usage is logged under its own provider key and,
being credit-based per the owner's choice, is not budget-capped here (add a cap the
same way if desired).

Records append to `settings.usage_path` (JSONL, thread-safe). This is the source of
truth for the `/costs` view and the Gemini cap.
"""
from __future__ import annotations

import json
import threading
from datetime import UTC, datetime

from resumaker.config import get_settings

_lock = threading.Lock()


def _use_db() -> bool:
    """In the cloud (Turso/libSQL) the usage log lives in the DB: a local JSONL file is per-instance
    and lost on scale-to-zero, and the worker (which runs the LLM) and the API (which shows Metrics)
    are different instances. Local dev/tests keep the simple JSONL file."""
    s = get_settings()
    return bool(s.turso_url) or s.db_backend == "libsql"


class BudgetExceeded(RuntimeError):
    """Raised when a Gemini API call would exceed the configured budget."""


def _usage_path():
    p = get_settings().usage_path
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.touch()
    return p


def _iter_records():
    with _usage_path().open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def gemini_total() -> float:
    """Sum of recorded Gemini API cost so far (USD)."""
    if _use_db():
        from resumaker.persistence import db
        return db.usage_gemini_total()
    return sum(float(r.get("cost_usd", 0.0) or 0.0)
               for r in _iter_records() if r.get("provider") == "gemini")


def check_gemini(est_cost_usd: float = 0.0) -> None:
    """Raise BudgetExceeded if current Gemini spend (+estimate) exceeds the cap."""
    cap = get_settings().gemini_budget_usd
    total = gemini_total()
    if total + est_cost_usd >= cap:
        raise BudgetExceeded(
            f"Gemini budget cap ${cap:.2f} would be exceeded: spent ${total:.4f}, "
            f"this call est ${est_cost_usd:.4f}. Use the Claude CLI provider instead."
        )


def record(provider: str, model: str, in_tok: int, out_tok: int,
           cost_usd: float, task: str = "") -> None:
    """Append a usage record. Thread-safe."""
    rec = {
        "ts": datetime.now(UTC).isoformat(),
        "provider": provider,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(float(cost_usd or 0.0), 6),
        "task": task,
    }
    if _use_db():
        try:
            from resumaker.persistence import db
            db.record_usage(ts=rec["ts"], provider=provider, model=model, input_tokens=in_tok,
                            output_tokens=out_tok, cost_usd=rec["cost_usd"], task=task)
            return
        except Exception:  # noqa: BLE001 - usage logging must never break an LLM call; fall back to file
            pass
    with _lock, _usage_path().open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def summary() -> dict:
    """Aggregate usage per provider + the Gemini budget headroom."""
    if _use_db():
        from resumaker.persistence import db
        agg = db.usage_summary()
    else:
        agg = {}
        for rec in _iter_records():
            p = rec.get("provider", "unknown")
            a = agg.setdefault(p, {"calls": 0, "input_tokens": 0,
                                   "output_tokens": 0, "cost_usd": 0.0})
            a["calls"] += 1
            a["input_tokens"] += int(rec.get("input_tokens", 0) or 0)
            a["output_tokens"] += int(rec.get("output_tokens", 0) or 0)
            a["cost_usd"] += float(rec.get("cost_usd", 0.0) or 0.0)
        for a in agg.values():
            a["cost_usd"] = round(a["cost_usd"], 6)
    cap = get_settings().gemini_budget_usd
    spent = gemini_total()
    agg["_gemini_budget"] = {
        "cap_usd": cap,
        "spent_usd": round(spent, 6),
        "remaining_usd": round(cap - spent, 6),
    }
    return agg
