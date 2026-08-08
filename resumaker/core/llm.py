"""LLM provider abstraction.

Two providers, one interface:
  - ClaudeCLIProvider  -> shells out to the `claude` CLI (owner's subscription,
                          not counted against the Gemini API budget). DEFAULT.
  - GeminiProvider     -> Google Gemini API (paid; hard-capped at $5 via cost_guard).

All calls go through `complete()` / `complete_json()`. Never import the Gemini
SDK or spawn `claude` directly elsewhere -- use this module so cost tracking and
the budget cap always apply.

Run modules from the `resumaker/` dir (`uv run python -m ...`) so imports resolve
as `core.*`, `pocs.*`, `evals.*`.

Usage:
    from core.llm import get_provider
    llm = get_provider()                      # Claude CLI, cheap model (haiku)
    out = llm.complete_json("Extract keywords...", task="keywords")
    # for accuracy-critical steps (tailoring/fact-checking):
    llm = get_provider("claude", model="claude-opus-4-8")
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from . import cost_guard

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# ---- Gemini pricing (USD per 1M tokens), approximate 2026 list prices. ----
# Used only to estimate/record cost; keep conservative. Unknown models fall back
# to the flash rate.
GEMINI_PRICING = {
    "gemini-2.5-flash":            {"in": 0.30, "out": 2.50},
    "gemini-flash-latest":         {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite":       {"in": 0.10, "out": 0.40},
    "gemini-flash-lite-latest":    {"in": 0.10, "out": 0.40},
    "gemini-2.5-pro":              {"in": 1.25, "out": 10.00},
    "gemini-2.0-flash-lite":       {"in": 0.075, "out": 0.30},
    "gemini-3-flash-preview":      {"in": 0.30, "out": 2.50},
    "gemini-3.1-flash-lite-preview": {"in": 0.10, "out": 0.40},
    "_default":                    {"in": 0.30, "out": 2.50},
}


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of an LLM response (handles ```json fences)."""
    if not text:
        raise ValueError("empty response, no JSON")
    t = text.strip()
    # strip markdown code fences
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    # direct parse
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # find first balanced { } or [ ]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = t.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(t)):
            if t[i] == open_ch:
                depth += 1
            elif t[i] == close_ch:
                depth -= 1
                if depth == 0:
                    return json.loads(t[start:i + 1])
    raise ValueError(f"no JSON found in response: {text[:200]!r}")


class LLMProvider:
    name = "base"

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        raise NotImplementedError

    def complete_json(self, prompt: str, *, system: str | None = None,
                      temperature: float = 0.0, max_tokens: int = 4096,
                      task: str = "", retries: int = 2) -> Any:
        """Complete and parse JSON, retrying with a repair nudge on failure."""
        json_instruction = (
            "\n\nReturn ONLY valid JSON. No prose, no markdown fences, no explanation."
        )
        last_err: Exception | None = None
        p = prompt + json_instruction
        for attempt in range(retries + 1):
            resp = self.complete(p, system=system, temperature=temperature,
                                 max_tokens=max_tokens, task=task)
            try:
                return extract_json(resp.text)
            except (ValueError, json.JSONDecodeError) as e:
                last_err = e
                p = (prompt + json_instruction +
                     f"\n\nYour previous reply was not valid JSON ({e}). "
                     "Reply again with ONLY the JSON.")
        raise ValueError(f"failed to get valid JSON after {retries + 1} tries: {last_err}")


class ClaudeCLIProvider(LLMProvider):
    """Runs the local `claude` CLI headlessly. Uses the owner's subscription.

    Cost is logged (from total_cost_usd) for visibility but recorded under
    provider='claude', so it never blocks on the Gemini budget cap.
    """
    name = "claude"

    def __init__(self, model: str = "claude-haiku-4-5", timeout_s: int = 240,
                 cwd: str | None = None, retries: int = 4):
        self.model = model
        self.timeout_s = timeout_s
        self.cwd = cwd or str(REPO_ROOT)
        self.retries = retries

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        # `--tools ""` disables ALL built-in tools: these are pure text-generation
        # calls, so the model must never attempt tool use (which wastes the single
        # turn and returns is_error/stop_reason=tool_use).
        cmd = ["claude", "-p", prompt, "--output-format", "json",
               "--max-turns", "1", "--model", self.model, "--tools", ""]
        if system:
            cmd += ["--append-system-prompt", system]
        # Retry transient CLI failures (rc!=0, empty stdout, JSON parse) with
        # backoff -- headless invocations occasionally blip under concurrency.
        last_err = ""
        t0 = time.time()
        for attempt in range(self.retries):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=self.timeout_s, cwd=self.cwd)
            except subprocess.TimeoutExpired as e:
                last_err = f"timeout after {self.timeout_s}s"
                time.sleep(1.5 * (attempt + 1))
                continue
            if proc.returncode != 0 or not proc.stdout.strip():
                last_err = f"rc={proc.returncode}: {proc.stderr.strip()[:300]}"
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                obj = json.loads(proc.stdout.strip())
            except json.JSONDecodeError as e:
                last_err = f"JSON parse: {e}; stdout={proc.stdout[:200]!r}"
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        else:
            raise RuntimeError(
                f"claude CLI failed after {self.retries} attempts: {last_err}")
        latency = time.time() - t0
        if obj.get("is_error"):
            raise RuntimeError(f"claude CLI returned error: {obj.get('result', '')[:300]}")
        usage = obj.get("usage", {}) or {}
        in_tok = int(usage.get("input_tokens", 0) or 0) + \
            int(usage.get("cache_read_input_tokens", 0) or 0) + \
            int(usage.get("cache_creation_input_tokens", 0) or 0)
        out_tok = int(usage.get("output_tokens", 0) or 0)
        cost = float(obj.get("total_cost_usd", 0.0) or 0.0)
        cost_guard.record("claude", self.model, in_tok, out_tok, cost, task)
        return LLMResponse(
            text=obj.get("result", ""), provider=self.name, model=self.model,
            input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            latency_s=latency, raw=obj,
        )


class GeminiProvider(LLMProvider):
    """Google Gemini API. Hard-capped at $5 cumulative via cost_guard."""
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        from google import genai  # lazy import (new google-genai SDK)
        self._client = genai.Client(api_key=api_key)

    def _price(self) -> dict:
        return GEMINI_PRICING.get(self.model, GEMINI_PRICING["_default"])

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        from google.genai import types
        # Pre-flight budget check with a rough input estimate (~4 chars/token).
        price = self._price()
        est_in = (len(prompt) + len(system or "")) / 4
        est_cost = (est_in / 1e6) * price["in"] + (max_tokens / 1e6) * price["out"]
        cost_guard.check_gemini(est_cost)

        cfg_kwargs = dict(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system or None,
        )
        # Gemini 2.5+ "thinking" can consume the whole output budget on small
        # max_tokens, yielding empty text. Disable it for our deterministic
        # extraction/tailoring calls (we want the answer, not hidden reasoning).
        try:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass
        cfg = types.GenerateContentConfig(**cfg_kwargs)
        t0 = time.time()
        resp = self._client.models.generate_content(
            model=self.model, contents=prompt, config=cfg)
        latency = time.time() - t0
        um = getattr(resp, "usage_metadata", None)
        in_tok = int(getattr(um, "prompt_token_count", 0) or 0)
        out_tok = int(getattr(um, "candidates_token_count", 0) or 0)
        cost = (in_tok / 1e6) * price["in"] + (out_tok / 1e6) * price["out"]
        cost_guard.record("gemini", self.model, in_tok, out_tok, cost, task)
        return LLMResponse(
            text=resp.text or "", provider=self.name, model=self.model,
            input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            latency_s=latency, raw={},
        )


def get_provider(name: str = "claude", **kwargs) -> LLMProvider:
    """Factory. Default = Claude CLI (subscription, no API cost)."""
    name = (name or "claude").lower()
    if name in ("claude", "claude_cli", "cli"):
        return ClaudeCLIProvider(**kwargs)
    if name in ("gemini", "google"):
        return GeminiProvider(**kwargs)
    raise ValueError(f"unknown provider: {name!r}")
