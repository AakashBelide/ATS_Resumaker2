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


# `_env_file=None` keeps these hermetic (a real repo `.env` can't leak a Turso URL in).
def test_turso_remote_only_auto_enabled_when_url_set(monkeypatch, tmp_path):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://db.turso.io")
    monkeypatch.delenv("RESUMAKER_TURSO_REMOTE_ONLY", raising=False)
    s = Settings(root_dir=tmp_path, _env_file=None)
    assert s.turso_url == "libsql://db.turso.io"
    assert s.turso_remote_only is True  # forced on: a Turso URL implies prod


def test_turso_remote_only_respects_explicit_false(monkeypatch, tmp_path):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://db.turso.io")
    monkeypatch.setenv("RESUMAKER_TURSO_REMOTE_ONLY", "false")
    s = Settings(root_dir=tmp_path, _env_file=None)
    assert s.turso_remote_only is False  # explicit opt-out still wins


def test_turso_remote_only_stays_off_without_url(monkeypatch, tmp_path):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("RESUMAKER_TURSO_REMOTE_ONLY", raising=False)
    s = Settings(root_dir=tmp_path, _env_file=None)
    assert s.turso_url is None
    assert s.turso_remote_only is False  # no Turso URL -> default stays off


def test_run_pipeline_reuses_provided_keyword_set_and_gap(tmp_settings, monkeypatch):
    """Generation reuses a match's report.json by passing keyword_set/gap (and job) into the
    pipeline: those stages — plus scrape + structure — must be SKIPPED, not re-run."""
    from types import SimpleNamespace

    from resumaker.domain import ApplyDecision, FitScore, GapReport, JobPosting, KeywordSet
    from resumaker.pipeline import orchestrator

    def boom(*a, **k):
        raise AssertionError("stage must be SKIPPED when its result is provided")

    # scrape/structure skipped by `job=`; keywords/gap skipped by `keyword_set=`/`gap=`.
    monkeypatch.setattr(orchestrator, "scrape", boom)
    monkeypatch.setattr(orchestrator, "structure_jd", boom)
    monkeypatch.setattr(orchestrator, "extract_keywords", boom)
    monkeypatch.setattr(orchestrator, "analyze_gaps", boom)
    # the stages that DO run in a match get cheap stand-ins (no real LLM calls).
    monkeypatch.setattr(orchestrator, "sponsor_signal", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "resolve_sponsorship", lambda *a, **k: SimpleNamespace(verdict="ok"))
    monkeypatch.setattr(orchestrator, "score_fit", lambda *a, **k: FitScore(final_0_100=70.0))
    monkeypatch.setattr(orchestrator, "decide_apply", lambda *a, **k: ApplyDecision(recommend_apply=True))

    job = JobPosting(title="ML Engineer", company="ACME", raw_text="jd body text")
    ks = KeywordSet(standardized=["python"])
    gap = GapReport()
    res = orchestrator.run_pipeline(url="https://x.co/j", job=job, keyword_set=ks, gap=gap,
                                    match_only=True, parallel=False, run_id="reuse-1")
    assert res.error == ""                       # no boom-ing (skipped) stage fired
    assert res.keyword_set is ks and res.gap is gap
    assert res.fit.final_0_100 == 70.0


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


def test_update_profile_fact_writes_to_db(tmp_settings, monkeypatch):
    """The canonical profile store is the DB document. update_profile_fact (no explicit file path)
    must write THERE so the app + profile agent actually see the change - not a stale JSON file the
    rest of the app never reads (the bug where agent edits never reached the summary/document)."""
    from resumaker.enrichment import manager
    from resumaker.persistence import profile as prof
    db.init_db()
    monkeypatch.setattr(manager, "record_enrichment", lambda *a, **k: {})   # keep the audit log out of tmp
    prof.invalidate()
    prof.save_profile({"skills": {"Frontend": ["React"]}, "projects": []})
    manager.update_profile_fact(["skills", "Frontend"], ["React", "Next.js"], reason="test")
    assert db.get_document("profile")["skills"]["Frontend"] == ["React", "Next.js"]
    assert prof.load_profile()["skills"]["Frontend"] == ["React", "Next.js"]   # and it's visible via the cache


def test_seed_profile_deterministic(tmp_settings, monkeypatch):
    """The first-time deterministic seed loads a filled template straight into the DB (no LLM), and
    the template it hands out must itself be a valid, seedable document once filled."""
    from resumaker.persistence import profile as prof
    # isolate the profile module too: without this its _load_doc falls back to the real profile file
    monkeypatch.setattr("resumaker.persistence.profile.get_settings", lambda: tmp_settings)
    db.init_db()
    prof.invalidate()
    assert prof.is_seeded() is False
    doc = prof.profile_template()
    summary = prof.seed_profile(doc)                    # the example template is a usable profile
    assert summary["experience"] == 1 and summary["projects"] == 1
    assert prof.is_seeded() is True
    saved = prof.load_profile()
    assert "_help" not in saved and saved["_meta"].get("seeded")     # guidance stripped, stamped
    # a doc with no experience/projects/skills is rejected
    with pytest.raises(ValueError, match="empty"):
        prof.seed_profile({"contact": {"name": "x"}})
    # wrong types are rejected
    with pytest.raises(ValueError, match="list"):
        prof.seed_profile({"experience": "not a list"})


def test_seed_profile_normalizes_garbage(tmp_settings, monkeypatch):
    """Valid JSON with messy nested shapes must be coerced (not saved raw) so tailoring/rendering,
    which read e['bullets'][i]['text'], can't crash on a string bullet or a non-dict entry."""
    from resumaker.persistence import profile as prof
    monkeypatch.setattr("resumaker.persistence.profile.get_settings", lambda: tmp_settings)
    db.init_db()
    prof.invalidate()
    messy = {
        "experience": [
            {"title": "MLE", "bullets": ["a plain-string bullet", {"text": "kept"}, {"text": ""}]},
            "this entry is a string, not a dict",          # dropped
        ],
        "skills": {"Lang": ["Python", "  "], "Bad": "not-a-list"},   # blank dropped, non-list category dropped
    }
    prof.seed_profile(messy)
    saved = prof.load_profile()
    exp = saved["experience"]
    assert len(exp) == 1                                    # the string entry was dropped
    assert all(isinstance(b, dict) and b["text"] for b in exp[0]["bullets"])   # strings coerced, empties gone
    assert [b["text"] for b in exp[0]["bullets"]] == ["a plain-string bullet", "kept"]
    assert exp[0]["organization"] == ""                     # missing keys defaulted
    assert saved["skills"] == {"Lang": ["Python"]}          # blank + non-list pruned


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


def test_llm_usage_log_db(tmp_settings):
    """Durable per-provider usage log in the DB (used in cloud so usage survives scale-to-zero and
    is visible from the API even though the worker recorded it)."""
    db.init_db()
    db.record_usage(ts="2026-08-12T00:00:00+00:00", provider="claude", model="opus",
                    input_tokens=100, output_tokens=50, cost_usd=0.0, task="tailor")
    db.record_usage(ts="2026-08-12T00:01:00+00:00", provider="gemini", model="flash",
                    input_tokens=200, output_tokens=80, cost_usd=0.012, task="fallback")
    s = db.usage_summary()
    assert s["claude"]["calls"] == 1 and s["claude"]["input_tokens"] == 100
    assert s["gemini"]["cost_usd"] == 0.012 and s["gemini"]["output_tokens"] == 80
    assert db.usage_gemini_total() == 0.012


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


def test_local_artifact_purge_by_suffix(tmp_settings, monkeypatch):
    """purge() drops a run's stale resume artifacts (a previously generated .pdf/.docx) so an
    uploaded PDF can replace them, but leaves other files (report.json) untouched."""
    from resumaker.persistence import artifacts
    monkeypatch.setattr("resumaker.persistence.artifacts.get_settings", lambda: tmp_settings)
    store = artifacts.LocalArtifactStore()
    d = store.local_run_dir("r10")
    (d / "acme-mle-resume.pdf").write_text("x")
    (d / "acme-mle-resume.docx").write_text("y")
    (d / "report.json").write_text("{}")
    store.purge("r10", (".pdf", ".docx"))
    assert store.find("r10", ".pdf") is None and store.find("r10", ".docx") is None
    assert (d / "report.json").is_file()          # non-matching files survive
    store.purge("missing-run", (".pdf",))          # no-op on an absent run dir (must not raise)


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
