"""R3 provider-layer tests. No network/LLM: a fake provider exercises the registry,
cache wrapper, and JSON extraction. Live provider calls live in tests/integration."""
from __future__ import annotations

import pytest

from resumaker.config import Settings
from resumaker.providers.llm.base import LLMProvider, LLMResponse, extract_json
from resumaker.providers.llm.cache import CachedProvider
from resumaker.providers.sources import available_sources, get_source


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, model: str = "m"):
        self.model = model
        self.calls = 0

    def complete(self, prompt, *, system=None, temperature=0.0, max_tokens=4096, task=""):
        self.calls += 1
        return LLMResponse(text=f'{{"n": {self.calls}}}', provider="fake", model=self.model)


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    s = Settings(root_dir=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr("resumaker.persistence.cache.get_settings", lambda: s)
    return s


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('here you go: {"a": [1,2]} thanks') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_complete_json_shared_on_base():
    fake = FakeProvider()
    assert fake.complete_json("give me json") == {"n": 1}


def test_cache_wrapper_memoizes_deterministic_calls(tmp_cache):
    fake = FakeProvider()
    cached = CachedProvider(fake)
    r1 = cached.complete("same prompt", task="t")
    assert r1.cached is False and fake.calls == 1
    r2 = cached.complete("same prompt", task="t")
    assert r2.cached is True and fake.calls == 1   # served from disk, no 2nd call
    assert r2.text == r1.text


def test_cache_wrapper_bypasses_nonzero_temperature(tmp_cache):
    fake = FakeProvider()
    cached = CachedProvider(fake)
    cached.complete("p", temperature=0.7)
    cached.complete("p", temperature=0.7)
    assert fake.calls == 2  # never cached


def test_registry_rejects_unknown_provider():
    from resumaker.providers.llm import get_provider
    with pytest.raises(ValueError):
        get_provider("does-not-exist")


class _Boom(LLMProvider):
    name = "boom"

    def complete(self, prompt, *, system=None, temperature=0.0, max_tokens=4096, task=""):
        raise RuntimeError("rate limited")


def test_fallback_provider_fails_over_and_is_lazy():
    """FallbackProvider only builds the fallback when the primary actually fails, then routes
    to it - and complete_json (base) rides the same failover."""
    from resumaker.providers.llm.registry import FallbackProvider

    built = {"n": 0}

    def factory():
        built["n"] += 1
        return FakeProvider()

    fb = FallbackProvider(_Boom(), factory)
    assert built["n"] == 0                       # lazy: not built until needed
    assert fb.name == "boom"                     # identity of the primary (cost attribution)
    r = fb.complete("hi", task="t")              # fallback call #1
    assert r.provider == "fake" and built["n"] == 1
    fb.complete("again")                         # #2 - fallback reused, not rebuilt
    assert built["n"] == 1
    assert fb.complete_json("give me json") == {"n": 3}   # #3, base.complete_json -> failover


def test_get_provider_wraps_with_fallback_when_configured(monkeypatch):
    from resumaker.providers.llm import registry

    s = Settings(default_provider="claude", fallback_provider="gemini")
    monkeypatch.setattr(registry, "get_settings", lambda: s)
    # don't actually build claude/gemini - stub the builder
    monkeypatch.setattr(registry, "_build", lambda name, **kw: FakeProvider(model=name))

    p = registry.get_provider("claude", cache=False)
    assert isinstance(p, registry.FallbackProvider)
    # no fallback wrapping when none configured
    s2 = Settings(default_provider="claude", fallback_provider=None)
    monkeypatch.setattr(registry, "get_settings", lambda: s2)
    p2 = registry.get_provider("claude", cache=False)
    assert not isinstance(p2, registry.FallbackProvider)


def test_sources_registry():
    assert "greenhouse" in available_sources()
    assert get_source("greenhouse").source == "greenhouse"
    with pytest.raises(ValueError):
        get_source("nope")
