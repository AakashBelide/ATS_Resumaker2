"""Cost guard: tracks LLM spend and enforces a hard cap on Gemini API usage.

Claude CLI usage is logged (for visibility into subscription burn) but does NOT
count against the Gemini API budget cap, since it uses the owner's Claude
subscription rather than paid API tokens.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
USAGE_FILE = REPO_ROOT / "data" / "cache" / "usage.jsonl"

# Hard cap on cumulative Gemini *API* spend (USD). Per owner: must not exceed $5.
GEMINI_BUDGET_USD = 5.0

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    """Raised when a Gemini API call would exceed the configured budget."""


def _ensure_file() -> None:
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USAGE_FILE.exists():
        USAGE_FILE.touch()


def gemini_total() -> float:
    """Sum of recorded Gemini API cost so far (USD)."""
    _ensure_file()
    total = 0.0
    with USAGE_FILE.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("provider") == "gemini":
                total += float(rec.get("cost_usd", 0.0) or 0.0)
    return total


def check_gemini(est_cost_usd: float = 0.0) -> None:
    """Raise BudgetExceeded if current Gemini spend (+estimate) exceeds the cap."""
    total = gemini_total()
    if total + est_cost_usd >= GEMINI_BUDGET_USD:
        raise BudgetExceeded(
            f"Gemini budget cap ${GEMINI_BUDGET_USD:.2f} would be exceeded: "
            f"spent ${total:.4f}, this call est ${est_cost_usd:.4f}. "
            f"Use the Claude CLI provider instead."
        )


def record(provider: str, model: str, in_tok: int, out_tok: int,
           cost_usd: float, task: str = "") -> None:
    """Append a usage record. Thread-safe."""
    _ensure_file()
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(float(cost_usd or 0.0), 6),
        "task": task,
    }
    with _lock:
        with USAGE_FILE.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")


def summary() -> dict:
    """Aggregate usage for a quick report."""
    _ensure_file()
    agg: dict[str, dict] = {}
    with USAGE_FILE.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = rec.get("provider", "unknown")
            a = agg.setdefault(p, {"calls": 0, "input_tokens": 0,
                                   "output_tokens": 0, "cost_usd": 0.0})
            a["calls"] += 1
            a["input_tokens"] += int(rec.get("input_tokens", 0) or 0)
            a["output_tokens"] += int(rec.get("output_tokens", 0) or 0)
            a["cost_usd"] += float(rec.get("cost_usd", 0.0) or 0.0)
    for a in agg.values():
        a["cost_usd"] = round(a["cost_usd"], 6)
    agg["_gemini_budget"] = {
        "cap_usd": GEMINI_BUDGET_USD,
        "spent_usd": round(gemini_total(), 6),
        "remaining_usd": round(GEMINI_BUDGET_USD - gemini_total(), 6),
    }
    return agg


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
