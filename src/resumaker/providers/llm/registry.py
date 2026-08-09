"""LLM provider registry - the ONE factory the whole codebase calls.

`get_provider()` picks the engine (default from settings) and, when caching is enabled,
transparently wraps it so deterministic calls are memoized. Stages never name a concrete
provider class; they call `get_provider(model=...)` and stay engine-agnostic, so switching
Claude-CLI <-> Anthropic-API <-> Gemini is a config change, not a code change.
"""
from __future__ import annotations

from resumaker.config import get_settings
from resumaker.observability import cost  # noqa: F401  (ensures budget module import path)
from resumaker.providers.llm.base import LLMProvider, LLMResponse, extract_json
from resumaker.providers.llm.cache import CachedProvider

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


def get_provider(name: str | None = None, *, cache: bool | None = None,
                 **kwargs) -> LLMProvider:
    """Factory. `name` defaults to settings.default_provider. Set `cache=False` to
    bypass the response cache for this provider instance."""
    s = get_settings()
    resolved = _ALIASES.get((name or s.default_provider).lower())
    if resolved is None:
        raise ValueError(f"unknown provider: {name!r}")
    provider = _build(resolved, **kwargs)
    use_cache = s.llm_cache_enabled if cache is None else cache
    return CachedProvider(provider) if use_cache else provider


__all__ = ["get_provider", "LLMProvider", "LLMResponse", "extract_json"]
