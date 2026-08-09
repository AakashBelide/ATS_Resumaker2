"""LLM provider interface + shared helpers.

Every provider implements `complete()`. `complete_json()` is shared here: it appends a
strict-JSON instruction and retries with a repair nudge, so all providers get robust
structured output for free. Never spawn `claude` or import an LLM SDK outside a provider
- go through the registry so cost tracking and the budget cap always apply.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    cached: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of an LLM response (handles ```json fences)."""
    if not text:
        raise ValueError("empty response, no JSON")
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
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
        for _ in range(retries + 1):
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
