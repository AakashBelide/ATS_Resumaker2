"""Central, env-driven configuration.

One `Settings` object is the single place that reads the environment. Everything
else imports `get_settings()` - no module reaches into `os.environ` directly, so
behavior is identical across local / VM / CI and is trivially overridable in tests.

Env vars use the `RESUMAKER_` prefix (e.g. `RESUMAKER_ENVIRONMENT=vm`). Provider
secrets keep their conventional unprefixed names (`ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`) so they interoperate with the SDKs and existing `.env`.
"""
from __future__ import annotations

import functools
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_root() -> Path:
    """Repo root = nearest ancestor containing pyproject.toml (falls back to CWD when
    installed standalone, e.g. inside a slim container without the source tree)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RESUMAKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- environment ---------------------------------------------------------
    environment: str = "local"  # local | vm | ci

    # -- filesystem (all overridable; defaults derive from the repo root) -----
    root_dir: Path = Field(default_factory=_find_root)
    data_dir: Path | None = None          # PII profile, prefs, sqlite, caches (gitignored)
    output_dir: Path | None = None        # generated run artifacts (gitignored)

    # -- LLM provider selection ---------------------------------------------
    # `default_provider` picks the engine for cognitive stages: claude | anthropic | gemini.
    # `claude` = Claude CLI (subscription, $0 tokens); `anthropic` = Anthropic API (credits).
    default_provider: str = "claude"
    model_fast: str = "claude-haiku-4-5"          # cheap extraction passes
    model_standard: str = "claude-sonnet-4-5"     # structuring / analysis
    model_quality: str = "claude-opus-4-8"        # tailoring / fact-critical
    gemini_model: str = "gemini-2.5-flash"
    gemini_budget_usd: float = 5.0                # hard cap on paid Gemini API spend
    llm_cache_enabled: bool = True

    # -- secrets (conventional unprefixed names) -----------------------------
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    # -- API service ---------------------------------------------------------
    api_token: str | None = None          # required to call the API when set (single-user auth)
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # -- watchlist ingestion + scheduler (RI) --------------------------------
    scheduler_enabled: bool = False       # if True, the API polls the watchlist on a cadence
    # Clean public JSON boards (Greenhouse/Lever/Ashby) have no bot protection - poll often.
    scheduler_interval_minutes: int = 60
    # Workday sits behind Akamai + throttles; poll it gently (daily) to avoid blocks.
    scheduler_workday_interval_minutes: int = 1440
    notify_webhook: str | None = None     # optional: POST a JSON digest of new jobs here

    @model_validator(mode="after")
    def _derive_paths(self) -> Settings:
        if self.data_dir is None:
            self.data_dir = self.root_dir / "data"
        if self.output_dir is None:
            self.output_dir = self.root_dir / "outputs"
        return self

    # -- convenience path accessors -----------------------------------------
    # `_derive_paths` guarantees these are set; the guarded accessors keep types clean.
    @property
    def data_root(self) -> Path:
        assert self.data_dir is not None
        return self.data_dir

    @property
    def output_root(self) -> Path:
        assert self.output_dir is not None
        return self.output_dir

    @property
    def profile_path(self) -> Path:
        return self.data_root / "profile" / "profile.json"

    @property
    def preferences_path(self) -> Path:
        return self.data_root / "profile" / "preferences.json"

    @property
    def house_rules_path(self) -> Path:
        return self.data_root / "profile" / "house_rules.json"

    @property
    def cache_dir(self) -> Path:
        return self.data_root / "cache"

    @property
    def usage_path(self) -> Path:
        return self.cache_dir / "usage.jsonl"

    @property
    def enrichment_log_path(self) -> Path:
        return self.cache_dir / "enrichment_log.jsonl"

    @property
    def db_path(self) -> Path:
        return self.data_root / "resumaker.db"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide singleton. Cached so `.env` is read once; call
    `get_settings.cache_clear()` in tests to re-read with a patched environment."""
    return Settings()
