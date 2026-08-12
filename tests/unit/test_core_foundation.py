"""R2 core-foundation unit tests. Use a tmp data_dir so nothing touches real PII."""
from __future__ import annotations

import pytest

from resumaker.config import Settings, get_settings
from resumaker.domain import JobRecord, PipelineResult, RunRecord
from resumaker.observability import cost, metrics
from resumaker.persistence import cache, db, files


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    """Point the process at an isolated data/output dir for the duration of a test."""
    s = Settings(root_dir=tmp_path, data_dir=tmp_path / "data",
                 output_dir=tmp_path / "outputs", gemini_budget_usd=5.0)
    monkeypatch.setattr("resumaker.config.settings.get_settings", lambda: s)
    for mod in (cost, cache, db, files):
        monkeypatch.setattr(f"{mod.__name__}.get_settings", lambda: s)
    return s


def test_settings_derives_paths(tmp_path):
    s = Settings(root_dir=tmp_path)
    assert s.data_dir == tmp_path / "data"
    assert s.output_dir == tmp_path / "outputs"
    assert s.profile_path.name == "profile.json"
    assert s.db_path.name == "resumaker.db"


def test_get_settings_is_cached():
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_slugify():
    assert files.slugify("State Street", "AI Orchestration Engineer") == \
        "state-street-ai-orchestration-engineer"
    assert files.slugify("Café / Résumé!!") == "caf-rsum"
    assert files.slugify("") == "run"


def test_cache_roundtrip(tmp_settings):
    key = cache.make_key("claude", "opus", {"b": 2, "a": 1})
    assert cache.make_key("claude", "opus", {"a": 1, "b": 2}) == key  # order-stable
    assert cache.get("llm", key) is None
    cache.put("llm", key, {"text": "hi"})
    assert cache.get("llm", key) == {"text": "hi"}


def test_cost_guard_records_and_caps(tmp_settings):
    assert cost.gemini_total() == 0.0
    cost.record("claude", "opus", 100, 50, 0.03, "tailor")  # not counted vs cap
    cost.record("gemini", "flash", 1000, 500, 1.5, "embed")
    assert cost.gemini_total() == pytest.approx(1.5)
    cost.check_gemini(1.0)  # 1.5 + 1.0 = 2.5 < 5, ok
    with pytest.raises(cost.BudgetExceeded):
        cost.check_gemini(4.0)  # 1.5 + 4.0 = 5.5 >= 5
    summ = cost.summary()
    assert summ["claude"]["calls"] == 1
    assert summ["_gemini_budget"]["remaining_usd"] == pytest.approx(3.5)


def test_db_run_upsert(tmp_settings):
    db.init_db()
    run = RunRecord(id="r1", url="http://x", out_dir="/o", status="running")
    db.record_run(run)
    got = db.get_run("r1")
    assert got and got.status == "running"
    run.status = "done"
    run.recommend_apply = True
    run.fit_0_100 = 77.0
    db.record_run(run)
    got = db.get_run("r1")
    assert got.status == "done" and got.recommend_apply is True and got.fit_0_100 == 77.0
    assert len(db.list_runs()) == 1


def test_db_run_record_serializes_datetimes(tmp_settings):
    """record_run must serialize datetime timestamps to ISO strings before binding: the
    libSQL/Turso driver rejects datetime params ("Unsupported parameter type"), which silently
    dropped every generation run's row in the cloud. `_index_run` passes real datetimes, so this
    path must not raise and must round-trip."""
    from datetime import UTC, datetime

    from resumaker.persistence.db import _iso

    assert _iso(None) is None
    assert _iso("2026-08-12T00:00:00+00:00") == "2026-08-12T00:00:00+00:00"
    ts = datetime(2026, 8, 12, 15, 30, tzinfo=UTC)
    assert _iso(ts) == ts.isoformat()

    db.init_db()
    run = RunRecord(id="dt1", url="http://x", out_dir="/o", status="done",
                    created_at=ts, finished_at=ts)
    db.record_run(run)  # would raise on the libSQL backend if datetimes weren't serialized
    got = db.get_run("dt1")
    assert got is not None and got.created_at == ts and got.finished_at == ts


def test_set_run_status_updates_in_place_and_inserts(tmp_settings):
    """set_run_status flips status without clobbering the row (a reused run_id keeps its out_dir),
    and inserts a minimal row when the run isn't indexed yet."""
    db.init_db()
    db.record_run(RunRecord(id="s1", url="http://x", out_dir="/o/s1", status="matched"))
    db.set_run_status("s1", "running")
    got = db.get_run("s1")
    assert got is not None and got.status == "running" and got.out_dir == "/o/s1"

    db.set_run_status("s2", "running", "http://y")   # insert-if-missing path
    got2 = db.get_run("s2")
    assert got2 is not None and got2.status == "running" and got2.url == "http://y"


def test_local_artifact_find_by_suffix(tmp_settings, monkeypatch):
    """find() resolves a role-slug artifact (resume PDF/DOCX) by suffix - the path used to serve
    resume.pdf/docx (which have company-role filenames, not a fixed name)."""
    from resumaker.persistence import artifacts
    monkeypatch.setattr("resumaker.persistence.artifacts.get_settings", lambda: tmp_settings)
    store = artifacts.LocalArtifactStore()
    d = store.local_run_dir("r9")
    (d / "morgan-stanley-ai-engineer-resume.pdf").write_text("x")
    (d / "morgan-stanley-ai-engineer-resume.docx").write_text("y")
    assert store.find("r9", ".pdf") == "morgan-stanley-ai-engineer-resume.pdf"
    assert store.find("r9", ".docx") == "morgan-stanley-ai-engineer-resume.docx"
    assert store.find("r9", ".txt") is None


def test_ensure_column_tolerates_stale_duplicate(tmp_settings):
    """_ensure_column swallows a 'duplicate column' ALTER error (libSQL/Turso stale-view case)
    but re-raises anything else. Reproduces the real-Turso first-run failure."""
    class _Rows(list):
        def fetchall(self): return self
    class _Conn:
        def __init__(self, alter_error): self._err = alter_error
        def execute(self, sql, *a):
            if sql.startswith("PRAGMA"):        # report the column ABSENT to force the ALTER
                return _Rows([{"name": "id"}])
            raise RuntimeError(self._err)       # ALTER fails
    # duplicate-column -> swallowed (column already exists remotely = success)
    db._ensure_column(_Conn("SQLite error: duplicate column name: posted_at"),  # type: ignore[arg-type]
                      "jobs", "posted_at", "posted_at TEXT")
    # any other error -> propagated
    with pytest.raises(RuntimeError):
        db._ensure_column(_Conn("disk I/O error"),  # type: ignore[arg-type]
                          "jobs", "posted_at", "posted_at TEXT")


def test_db_job_dedupe(tmp_settings):
    db.init_db()
    job = JobRecord(source="greenhouse", external_id="123", title="MLE", content_hash="h1")
    jid, is_new = db.upsert_job(job)
    assert is_new is True
    _, is_new = db.upsert_job(job)  # same hash -> not new/changed
    assert is_new is False
    job.content_hash = "h2"  # edited posting
    jid2, changed = db.upsert_job(job)
    assert jid2 == jid and changed is True
    assert len(db.list_jobs()) == 1  # still one row (deduped on source+external_id)


def test_metrics_exposition():
    metrics.reset()
    metrics.inc("runs_total", stage="resume")
    metrics.inc("runs_total", stage="resume")
    metrics.set_gauge("gemini_spent_usd", 0.02)
    out = metrics.render()
    assert 'runs_total{stage="resume"} 2.0' in out
    assert "gemini_spent_usd 0.02" in out


def test_pipeline_result_defaults():
    r = PipelineResult(url="http://x")
    assert r.gated_out is False and r.warnings == [] and r.job is None
