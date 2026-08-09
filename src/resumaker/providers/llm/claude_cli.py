"""Claude CLI provider: shells out to the local `claude` binary headlessly, using the
owner's subscription (no per-token API cost). Cost is logged for visibility but recorded
under provider='claude', so it never trips the Gemini budget cap.

Model aliases ('haiku'/'sonnet'/'opus') are passed straight through to `--model`; the CLI
resolves them to the current release. This is the default engine locally.
"""
from __future__ import annotations

import json
import subprocess
import time

from resumaker.config import get_settings
from resumaker.observability import cost
from resumaker.providers.llm.base import LLMProvider, LLMResponse


class ClaudeCLIProvider(LLMProvider):
    name = "claude"

    def __init__(self, model: str = "haiku", timeout_s: int = 240,
                 cwd: str | None = None, retries: int = 4):
        self.model = model
        self.timeout_s = timeout_s
        self.cwd = cwd or str(get_settings().root_dir)
        self.retries = retries

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        # `--tools ""` disables ALL built-in tools: these are pure text-generation calls,
        # so the model must never attempt tool use (which wastes the single turn and
        # returns is_error/stop_reason=tool_use).
        cmd = ["claude", "-p", prompt, "--output-format", "json",
               "--max-turns", "1", "--model", self.model, "--tools", ""]
        if system:
            cmd += ["--append-system-prompt", system]
        # Retry transient CLI blips (rc!=0, empty stdout, JSON parse) with backoff.
        last_err = ""
        t0 = time.time()
        obj: dict = {}
        for attempt in range(self.retries):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=self.timeout_s, cwd=self.cwd)
            except subprocess.TimeoutExpired:
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
        in_tok = (int(usage.get("input_tokens", 0) or 0)
                  + int(usage.get("cache_read_input_tokens", 0) or 0)
                  + int(usage.get("cache_creation_input_tokens", 0) or 0))
        out_tok = int(usage.get("output_tokens", 0) or 0)
        usd = float(obj.get("total_cost_usd", 0.0) or 0.0)
        cost.record("claude", self.model, in_tok, out_tok, usd, task)
        return LLMResponse(text=obj.get("result", ""), provider=self.name, model=self.model,
                           input_tokens=in_tok, output_tokens=out_tok, cost_usd=usd,
                           latency_s=latency, raw=obj)
