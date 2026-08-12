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
    # CLI-first EVERYWHERE (local + cloud): keep `claude` primary and set a paid API fallback
    # that the provider layer switches to automatically when the CLI fails / is rate-limited.
    # Unset by default (no fallback), so nothing breaks without an API key. claude | anthropic |
    # gemini. Cloud auth for the CLI is the OAuth token (CLAUDE_CODE_OAUTH_TOKEN).
    fallback_provider: str | None = None
    model_fast: str = "claude-haiku-4-5"          # cheap extraction passes
    model_standard: str = "claude-sonnet-4-5"     # structuring / analysis
    model_quality: str = "claude-opus-4-8"        # tailoring / fact-critical
    gemini_model: str = "gemini-2.5-flash"
    gemini_budget_usd: float = 5.0                # hard cap on paid Gemini API spend
    llm_cache_enabled: bool = True

    # -- secrets (conventional unprefixed names) -----------------------------
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    # -- persistence backend (dual-mode: local SQLite file OR hosted Turso/libSQL) ------------
    # "sqlite" (stdlib, local file — default) | "libsql" (libSQL driver). libSQL is auto-selected
    # when TURSO_DATABASE_URL is set (cloud); RESUMAKER_DB_BACKEND=libsql exercises the libSQL path
    # against a LOCAL file (no cloud account needed). Same SQL; db.py is backend-agnostic.
    db_backend: str = "sqlite"
    turso_url: str | None = Field(default=None, validation_alias="TURSO_DATABASE_URL")
    turso_auth_token: str | None = Field(default=None, validation_alias="TURSO_AUTH_TOKEN")
    # A Turso connect + full sync is a ~3s network round-trip, so we open ONE shared connection
    # and let libSQL auto-sync in the background every N seconds (reads then hit the local replica
    # in ~ms). Lower = fresher cross-instance reads; higher = fewer background syncs.
    turso_sync_interval_s: int = 60
    # Remote-only mode: skip the local embedded replica entirely and send every query straight to
    # the Turso primary over HTTP. On scale-to-zero Cloud Run this is the better fit - no full
    # re-sync on every cold start (so no cold-start lag) and Embedded Syncs stays ~0 - at the cost
    # of ~30-50ms network latency per query (fine for this low-QPS app). Always reads the latest.
    turso_remote_only: bool = False

    # -- API service ---------------------------------------------------------
    api_token: str | None = None          # required to call the API when set (single-user auth)
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # -- job queue (dual-mode: in-process ThreadPool OR Cloud Tasks) ---------------------------
    # "inprocess" (default): run pipelines on the local ThreadPoolExecutor. "cloud_tasks":
    # enqueue an HTTP task to the worker service (Cloud Run request-based). Cloud needs
    # gcp_project/region + tasks_queue + worker_url; local ignores them.
    job_queue: str = "inprocess"          # inprocess | cloud_tasks
    worker_url: str | None = None         # worker service base URL (Cloud Tasks HTTP target)
    tasks_queue: str = "resumaker-pipeline"  # Cloud Tasks queue id
    gcp_project: str | None = None
    gcp_region: str | None = None

    # -- artifact store (dual-mode: local disk OR GCS) ----------------------------------------
    # "local" (default): artifacts live under output_dir on disk. "gcs": the run still writes
    # to a local temp dir (LibreOffice needs a real FS), then publishes to a bucket; the API
    # serves a signed URL. Cloud needs gcs_bucket.
    artifact_backend: str = "local"       # local | gcs
    gcs_bucket: str | None = None

    # -- agentic onboarding (Phase C) ----------------------------------------
    # Deterministic-first always runs ($0, no sandbox). The sandboxed agent fallback is opt-in
    # (needs Docker + a Claude token); off => onboarding is deterministic-only.
    onboard_agent_enabled: bool = False
    onboard_max_turns: int = 60           # usage cap: agent tool-call loop
    onboard_time_limit_s: int = 2400      # time-based auto-kill (40 min)
    # Where the sandboxed resolve runs: "docker" (local Docker sandbox - default) or "actions"
    # (dispatch a GitHub Actions run; Cloud Run can't nest Docker, so cloud uses this). Actions
    # mode needs a repo + PAT with `actions:write` + `contents:write` (for adapter-draft PRs).
    onboard_runner: str = "docker"        # docker | actions
    github_repo: str | None = None        # "owner/name" for the Actions dispatch
    github_token: str | None = Field(default=None, validation_alias="RESUMAKER_GITHUB_TOKEN")
    github_workflow: str = "onboard.yml"  # workflow file to dispatch

    # -- watchlist ingestion + scheduler (RI) --------------------------------
    scheduler_enabled: bool = False       # if True, the API polls the watchlist on a cadence
    # Clean public JSON boards (Greenhouse/Lever/Ashby) have no bot protection - poll often.
    scheduler_interval_minutes: int = 60
    # Workday sits behind Akamai + throttles; poll it gently (daily) to avoid blocks.
    scheduler_workday_interval_minutes: int = 1440
    # A sweep fetches boards grouped by ATS source (== host): groups run concurrently up to
    # this many at a time, while companies *within* a group stay serial + jittered (same host).
    ingest_fetch_workers: int = 5
    # The Cloud Scheduler job whose cron the Mailer "frequency" control rewrites - the dedicated
    # email-digest job (decoupled from ingestion). Blank / non-cloud -> the sync is a no-op.
    mailer_scheduler_job: str = "resumaker-mailer"
    notify_webhook: str | None = None     # optional: POST a JSON digest of new jobs here
    # -- email digest of new on-target postings (all from .env; nothing hardcoded) -----------
    notify_to: str | None = None          # recipient; blank -> email disabled
    notify_from: str = "onboarding@resend.dev"   # verified-domain address for real deliverability
    resend_api_key: str | None = None     # if set -> send via Resend API (recommended)
    smtp_host: str | None = None          # else -> SMTP fallback (e.g. Gmail App Password)
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None

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
