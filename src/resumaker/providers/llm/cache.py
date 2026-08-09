"""Transparent response cache wrapper for any LLMProvider.

Wraps `complete()` and memoizes deterministic (temperature == 0) calls to the on-disk
cache, keyed by provider+model+system+prompt+max_tokens. A cache hit skips the real call
entirely - no latency, no cost recorded (correct: nothing was spent). Non-deterministic
calls (temperature > 0) always pass through.
"""
from __future__ import annotations

from resumaker.persistence import cache as store
from resumaker.providers.llm.base import LLMProvider, LLMResponse

_NAMESPACE = "llm"


class CachedProvider(LLMProvider):
    def __init__(self, inner: LLMProvider):
        self.inner = inner
        self.name = inner.name
        self.model = getattr(inner, "model", "")

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        if temperature != 0.0:
            return self.inner.complete(prompt, system=system, temperature=temperature,
                                       max_tokens=max_tokens, task=task)
        key = store.make_key(self.inner.name, getattr(self.inner, "model", ""),
                             system or "", prompt, max_tokens)
        hit = store.get(_NAMESPACE, key)
        if hit is not None:
            return LLMResponse(text=hit["text"], provider=self.inner.name,
                               model=hit.get("model", ""), cached=True)
        resp = self.inner.complete(prompt, system=system, temperature=temperature,
                                   max_tokens=max_tokens, task=task)
        store.put(_NAMESPACE, key, {"text": resp.text, "model": resp.model})
        return resp
