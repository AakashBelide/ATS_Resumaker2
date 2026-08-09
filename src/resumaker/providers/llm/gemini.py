"""Google Gemini API provider. Hard-capped at the configured budget via the cost guard.

Used for the optional `--semantic gemini` coverage mode, embeddings, and parity tests.
"""
from __future__ import annotations

import contextlib
import time

from resumaker.config import get_settings
from resumaker.observability import cost
from resumaker.providers.llm.base import LLMProvider, LLMResponse

# Approximate 2026 list prices (USD / 1M tokens). Unknown models fall back to flash.
_PRICING = {
    "gemini-2.5-flash":            {"in": 0.30, "out": 2.50},
    "gemini-flash-latest":         {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite":       {"in": 0.10, "out": 0.40},
    "gemini-2.5-pro":              {"in": 1.25, "out": 10.00},
    "_default":                    {"in": 0.30, "out": 2.50},
}


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str | None = None):
        s = get_settings()
        if not s.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set (required for the gemini provider)")
        self.model = model or s.gemini_model
        from google import genai  # lazy import (new google-genai SDK)
        self._client = genai.Client(api_key=s.gemini_api_key)

    def _price(self) -> dict:
        return _PRICING.get(self.model, _PRICING["_default"])

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        from google.genai import types
        price = self._price()
        est_in = (len(prompt) + len(system or "")) / 4  # ~4 chars/token
        est_cost = (est_in / 1e6) * price["in"] + (max_tokens / 1e6) * price["out"]
        cost.check_gemini(est_cost)  # pre-flight budget check

        cfg_kwargs: dict = {"temperature": temperature, "max_output_tokens": max_tokens,
                            "system_instruction": system or None}
        # Gemini 2.5+ "thinking" can consume the whole small output budget, yielding empty
        # text. Disable it for our deterministic extraction/tailoring calls.
        with contextlib.suppress(Exception):
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        cfg = types.GenerateContentConfig(**cfg_kwargs)
        t0 = time.time()
        resp = self._client.models.generate_content(
            model=self.model, contents=prompt, config=cfg)
        latency = time.time() - t0
        um = getattr(resp, "usage_metadata", None)
        in_tok = int(getattr(um, "prompt_token_count", 0) or 0)
        out_tok = int(getattr(um, "candidates_token_count", 0) or 0)
        usd = (in_tok / 1e6) * price["in"] + (out_tok / 1e6) * price["out"]
        cost.record("gemini", self.model, in_tok, out_tok, usd, task)
        return LLMResponse(text=resp.text or "", provider=self.name, model=self.model,
                           input_tokens=in_tok, output_tokens=out_tok, cost_usd=usd,
                           latency_s=latency)
