"""Anthropic API provider: the clean engine for a deployed/headless VM (no CLI auth).

Pays per token (credits) - the owner accepts API cost for deployment. Cost is logged
under provider='anthropic'. Model aliases ('haiku'/'sonnet'/'opus') resolve to concrete
model IDs from settings so callers can stay engine-agnostic; a full ID passes through
unchanged.
"""
from __future__ import annotations

import time

from resumaker.config import get_settings
from resumaker.observability import cost
from resumaker.providers.llm.base import LLMProvider, LLMResponse

# Approximate 2026 list prices (USD / 1M tokens), for cost logging only. Matched by the
# family substring in the resolved model id.
_PRICING = {
    "opus":   {"in": 15.0, "out": 75.0},
    "sonnet": {"in": 3.0,  "out": 15.0},
    "haiku":  {"in": 1.0,  "out": 5.0},
    "_default": {"in": 3.0, "out": 15.0},
}


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "sonnet"):
        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set (required for the anthropic provider)")
        self.model = self._resolve(model, s)
        from anthropic import Anthropic  # lazy import
        self._client = Anthropic(api_key=s.anthropic_api_key)

    @staticmethod
    def _resolve(model: str, s) -> str:
        return {"haiku": s.model_fast, "fast": s.model_fast,
                "sonnet": s.model_standard, "standard": s.model_standard,
                "opus": s.model_quality, "quality": s.model_quality}.get(model, model)

    def _price(self) -> dict:
        for fam, p in _PRICING.items():
            if fam in self.model:
                return p
        return _PRICING["_default"]

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        t0 = time.time()
        resp = self._client.messages.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            system=system or "", messages=[{"role": "user", "content": prompt}])
        latency = time.time() - t0
        text = "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", "") == "text")
        in_tok = int(getattr(resp.usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(resp.usage, "output_tokens", 0) or 0)
        price = self._price()
        usd = (in_tok / 1e6) * price["in"] + (out_tok / 1e6) * price["out"]
        cost.record("anthropic", self.model, in_tok, out_tok, usd, task)
        return LLMResponse(text=text, provider=self.name, model=self.model,
                           input_tokens=in_tok, output_tokens=out_tok, cost_usd=usd,
                           latency_s=latency)
