"""Shared test fixtures. Live tests (real network/LLM) are marked `@pytest.mark.live`
and skipped by default (see [tool.pytest.ini_options] addopts)."""
from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
