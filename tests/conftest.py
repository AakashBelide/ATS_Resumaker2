"""Shared test fixtures. Live tests (real network/LLM) are marked `@pytest.mark.live`
and skipped by default (see [tool.pytest.ini_options] addopts)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _hermetic_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not read the developer's `.env`. Real creds there (Turso, GCP project/region,
    worker URL, bucket) would otherwise leak in via pydantic-settings and: sync init_db() to
    hosted Turso (slow, flaky, and writes test rows to the LIVE DB), or flip the cloud seams on
    so 'missing config' assertions fail. Disable `.env` reading so Settings sees only its
    defaults + env vars a test sets explicitly. `RESUMAKER_DB_BACKEND=libsql` (a real env var)
    still exercises the libSQL driver against a LOCAL file, so that CI path is unaffected."""
    from resumaker.config.settings import Settings
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    from resumaker.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
