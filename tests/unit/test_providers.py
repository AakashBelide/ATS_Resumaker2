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


def test_sources_registry():
    assert "greenhouse" in available_sources()
    assert get_source("greenhouse").source == "greenhouse"
    with pytest.raises(ValueError):
        get_source("nope")
