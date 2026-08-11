"""LLM provider registry - the ONE factory the whole codebase calls.

`get_provider()` picks the engine (default from settings) and, when caching is enabled,
transparently wraps it so deterministic calls are memoized. Stages never name a concrete
provider class; they call `get_provider(model=...)` and stay engine-agnostic, so switching
Claude-CLI <-> Anthropic-API <-> Gemini is a config change, not a code change.
"""
from __future__ import annotations

from collections.abc import Callable

from resumaker.config import get_settings
from resumaker.observability import cost  # noqa: F401  (ensures budget module import path)
from resumaker.observability.logging import get_logger
from resumaker.providers.llm.base import LLMProvider, LLMResponse, extract_json
from resumaker.providers.llm.cache import CachedProvider

_log = get_logger("resumaker.llm.registry")

_ALIASES = {
    "claude": "claude", "claude_cli": "claude", "cli": "claude",
    "anthropic": "anthropic", "api": "anthropic",
    "gemini": "gemini", "google": "gemini",
}


def _build(name: str, **kwargs) -> LLMProvider:
    if name == "claude":
        from resumaker.providers.llm.claude_cli import ClaudeCLIProvider
        return ClaudeCLIProvider(**kwargs)
    if name == "anthropic":
        from resumaker.providers.llm.anthropic_api import AnthropicProvider
        return AnthropicProvider(**kwargs)
    if name == "gemini":
        from resumaker.providers.llm.gemini import GeminiProvider
        return GeminiProvider(**kwargs)
    raise ValueError(f"unknown provider: {name!r}")


class FallbackProvider(LLMProvider):
    """Primary provider with automatic failover to a second engine (D.8: CLI-first everywhere).

    On any error from the primary `complete()` (the Claude CLI raises after exhausting its own
    retries - rate-limit, timeout, non-zero exit), transparently retry the same call on a
    fallback engine. The fallback is built LAZILY on first need, so configuring a fallback the
    box can't construct (e.g. `gemini` with no GEMINI_API_KEY) never breaks the happy path - it
    only surfaces if the primary actually fails. Model names aren't portable across engines, so
    the fallback uses its own default model. `complete_json()` (from the base) routes through
    this `complete()`, so structured calls get failover for free."""

    def __init__(self, primary: LLMProvider, fallback_factory: Callable[[], LLMProvider]):
        self._primary = primary
        self._factory = fallback_factory
        self._fallback: LLMProvider | None = None
        self.name = primary.name

    def complete(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.0, max_tokens: int = 4096,
                 task: str = "") -> LLMResponse:
        try:
            return self._primary.complete(prompt, system=system, temperature=temperature,
                                          max_tokens=max_tokens, task=task)
        except Exception as e:  # noqa: BLE001 - any primary failure triggers failover
            if self._fallback is None:
                self._fallback = self._factory()  # misconfig raises here, only on real failure
            _log.warning("llm primary failed; falling back",
                         extra={"primary": self._primary.name, "fallback": self._fallback.name,
                                "task": task, "error": str(e)})
            return self._fallback.complete(prompt, system=system, temperature=temperature,
                                           max_tokens=max_tokens, task=task)


def get_provider(name: str | None = None, *, cache: bool | None = None,
                 **kwargs) -> LLMProvider:
    """Factory. `name` defaults to settings.default_provider. When `settings.fallback_provider`
    is set (and differs from the primary), the returned provider auto-fails-over to it. Set
    `cache=False` to bypass the response cache for this provider instance."""
    s = get_settings()
    resolved = _ALIASES.get((name or s.default_provider).lower())
    if resolved is None:
        raise ValueError(f"unknown provider: {name!r}")
    provider = _build(resolved, **kwargs)
    fb = _ALIASES.get((s.fallback_provider or "").lower()) if s.fallback_provider else None
    if fb and fb != resolved:
        # fallback uses its own default model (engine-specific names don't port); built lazily.
        def _make_fallback(fb_name: str = fb) -> LLMProvider:
            return _build(fb_name)
        provider = FallbackProvider(provider, _make_fallback)
    use_cache = s.llm_cache_enabled if cache is None else cache
    return CachedProvider(provider) if use_cache else provider


__all__ = ["get_provider", "LLMProvider", "LLMResponse", "extract_json"]
