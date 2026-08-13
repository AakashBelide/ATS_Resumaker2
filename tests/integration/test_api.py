"""R5 API tests via FastAPI TestClient. No real pipeline runs (the queue/worker is mocked);
an isolated tmp data dir keeps SQLite + PII off the real filesystem."""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from resumaker.config import get_settings
from resumaker.persistence import profile

# Minimal, fake profile so profile-dependent endpoints work hermetically (no real PII).
_FAKE_PROFILE = {
    "contact": {"name": "Test Candidate", "email": "t@example.com", "phone": "000"},
    "summary": "2+ years building things.",
    "experience": [{"title": "Engineer", "organization": "Acme",
                    "start_date": "2023", "end_date": "Present",
                    "bullets": [{"text": "Did work.", "metrics": []}]}],
    "projects": [], "skills": {"Languages": ["Python"]}, "education": [],
    "facts_allowlist": {}, "equivalence_map": {},
    "work_authorization": {"needs_sponsorship_future": True},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RESUMAKER_API_TOKEN", "secret")
    monkeypatch.setenv("RESUMAKER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RESUMAKER_OUTPUT_DIR", str(tmp_path / "outputs"))
    prof_dir = tmp_path / "data" / "profile"
    prof_dir.mkdir(parents=True)
    (prof_dir / "profile.json").write_text(json.dumps(_FAKE_PROFILE))
    get_settings.cache_clear()
    profile.invalidate()

    from apps.api.main import create_app
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()
    profile.invalidate()


def test_health_and_metrics_are_open(client):
    assert client.get("/health").json()["status"] == "ok"
    m = client.get("/metrics")
    assert m.status_code == 200 and "TYPE" in m.text or m.text == "\n"


def test_auth_required_when_token_set(client):
    assert client.get("/v1/runs").status_code == 401           # no token
    assert client.get("/v1/runs", headers={"X-API-Key": "wrong"}).status_code == 401
    ok = client.get("/v1/runs", headers={"X-API-Key": "secret"})
    assert ok.status_code == 200 and ok.json() == []           # empty run list


def test_bearer_header_accepted(client):
    r = client.get("/v1/costs", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200 and "_gemini_budget" in r.json()


def test_profile_summary_no_pii(client):
    r = client.get("/v1/profile/summary", headers={"X-API-Key": "secret"})
    assert r.status_code == 200
    body = r.json()
    assert "years_experience" in body and "employers" in body
    assert "contact" not in body and "phone" not in body  # never leak PII


def test_sources_and_watchlist(client):
    h = {"X-API-Key": "secret"}
    assert "greenhouse" in client.get("/v1/sources", headers=h).json()["sources"]
    r = client.post("/v1/companies", headers=h,
                    json={"name": "Databricks",
                          "boards": [{"source": "greenhouse", "token": "databricks"}]})
    assert r.status_code == 201 and r.json()["boards"] == 1
    assert any(c["name"] == "Databricks"
               for c in client.get("/v1/companies", headers=h).json())


def test_start_run_returns_id(client, monkeypatch):
    """start_run mints the id and hands off to the in-process queue (default)."""
    seen = {}
    monkeypatch.setattr("apps.api.jobs.worker.manager.submit",
                        lambda run_id, url, **opts: seen.update(run_id=run_id, url=url, opts=opts))
    r = client.post("/v1/runs", headers={"X-API-Key": "secret"},
                    json={"url": "https://boards.greenhouse.io/x/jobs/1"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "running" and len(body["run_id"]) == 12          # minted uuid
    assert seen["run_id"] == body["run_id"] and seen["url"].endswith("/jobs/1")  # queued
    assert seen["opts"]["target_pages"] == 1


def test_job_queue_seam_selects_by_config(monkeypatch):
    """Default is in-process; cloud_tasks needs its cloud params or it fails loudly."""
    from apps.api.jobs.queue import CloudTasksQueue, InProcessQueue, get_job_queue

    from resumaker.config import get_settings

    monkeypatch.setenv("RESUMAKER_JOB_QUEUE", "inprocess")
    get_settings.cache_clear()
    assert isinstance(get_job_queue(), InProcessQueue)

    monkeypatch.setenv("RESUMAKER_JOB_QUEUE", "cloud_tasks")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):            # missing gcp_project/region/worker_url
        get_job_queue()

    monkeypatch.setenv("RESUMAKER_GCP_PROJECT", "p")
    monkeypatch.setenv("RESUMAKER_GCP_REGION", "us-central1")
    monkeypatch.setenv("RESUMAKER_WORKER_URL", "https://worker.example")
    get_settings.cache_clear()
    assert isinstance(get_job_queue(), CloudTasksQueue)
    get_settings.cache_clear()


def test_worker_ingest_tick(client, monkeypatch):
    """The Cloud Scheduler target: one poll over the selected source set, returns a summary."""
    from types import SimpleNamespace

    # fake two boards, one with a new job — assert the count is summed, not the source internals
    fake = [SimpleNamespace(new_jobs=[{"x": 1}]), SimpleNamespace(new_jobs=[])]
    captured = {}

    def fake_run_tick(sources):
        captured["sources"] = sources
        return fake
    monkeypatch.setattr("resumaker.ingestion.scheduler.run_tick", fake_run_tick)

    r = client.post("/v1/worker/ingest-tick", headers={"X-API-Key": "secret"},
                    json={"sources": "fast"})
    assert r.status_code == 200
    assert r.json() == {"sources": "fast", "companies": 2, "new": 1}
    assert captured["sources"] is not None and "greenhouse" in captured["sources"]  # fast set


def test_worker_run_pipeline(client, monkeypatch):
    """The Cloud Tasks target: runs one pipeline synchronously and returns the persisted record."""
    from resumaker.domain import RunRecord

    def fake_run_pipeline(**kw):
        # simulate the orchestrator persisting a terminal run row under the supplied run_id
        from resumaker.persistence import db
        db.record_run(RunRecord(id=kw["run_id"], url=kw["url"], status="done", fit_0_100=71.0))
        return type("R", (), {"error": ""})()
    monkeypatch.setattr("apps.api.routers.worker.run_pipeline", fake_run_pipeline)

    r = client.post("/v1/worker/run-pipeline", headers={"X-API-Key": "secret"},
                    json={"url": "https://boards.greenhouse.io/x/jobs/1", "run_id": "wrk-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "wrk-1" and body["status"] == "done" and body["fit_0_100"] == 71.0


def test_worker_tracker_match(client, monkeypatch):
    """The Cloud Tasks target for a tracked entry's match: runs run_match_for on the worker."""
    seen = {}
    monkeypatch.setattr("resumaker.ingestion.tracker.run_match_for",
                        lambda eid: seen.setdefault("id", eid))
    r = client.post("/v1/worker/tracker-match", headers={"X-API-Key": "secret"},
                    json={"entry_id": 7})
    assert r.status_code == 200 and r.json() == {"entry_id": 7, "ok": True}
    assert seen["id"] == 7


def test_worker_mailer_tick(client, monkeypatch):
    """The dedicated mailer Cloud Scheduler target: emails the pending backlog, returns the count."""
    monkeypatch.setattr("resumaker.ingestion.notify.email_pending", lambda: 3)
    r = client.post("/v1/worker/mailer-tick", headers={"X-API-Key": "secret"})
    assert r.status_code == 200 and r.json() == {"emailed": 3}


def test_worker_endpoints_require_token(client):
    assert client.post("/v1/worker/ingest-tick", json={}).status_code == 401
    assert client.post("/v1/worker/run-pipeline", json={"url": "x"}).status_code == 401
    assert client.post("/v1/worker/mailer-tick").status_code == 401
    assert client.post("/v1/worker/tracker-match", json={"entry_id": 1}).status_code == 401


def test_artifact_store_seam_local_default(client):
    """The local store serves artifacts inline (url()==None) from the run dir; publish is a
    no-op. The GET endpoint streams the file."""
    from resumaker.persistence.artifacts import LocalArtifactStore, get_artifact_store
    store = get_artifact_store()
    assert isinstance(store, LocalArtifactStore)
    d = store.local_run_dir("run-art")
    (d / "report.json").write_text('{"ok": true}')
    assert store.url("run-art", "report.json") is None          # inline, no external URL
    assert store.open("run-art", "report.json") == b'{"ok": true}'
    store.publish("run-art")                                     # no-op, must not raise

    r = client.get("/v1/runs/run-art/artifacts/report.json", headers={"X-API-Key": "secret"})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_artifact_store_seam_selects_by_config(monkeypatch):
    from resumaker.config import get_settings
    from resumaker.persistence.artifacts import GCSArtifactStore, get_artifact_store

    monkeypatch.setenv("RESUMAKER_ARTIFACT_BACKEND", "gcs")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):            # gcs backend needs a bucket
        get_artifact_store()
    monkeypatch.setenv("RESUMAKER_GCS_BUCKET", "my-bucket")
    get_settings.cache_clear()
    assert isinstance(get_artifact_store(), GCSArtifactStore)
    get_settings.cache_clear()


def test_run_progress_is_polled_from_status_json(client):
    """Progress is served by polling `status.json` (not SSE), so any instance can report it."""
    h = {"X-API-Key": "secret"}
    out = get_settings().output_root / "run-xyz"
    out.mkdir(parents=True)
    (out / "status.json").write_text(json.dumps({
        "current": "tailor", "done": False, "elapsed": 12.5,
        "stages": [{"stage": "scrape", "status": "done", "detail": "", "elapsed": 2.0},
                   {"stage": "tailor", "status": "start", "detail": "", "elapsed": None}]}))
    p = client.get("/v1/runs/run-xyz/progress", headers=h)
    assert p.status_code == 200
    body = p.json()
    assert body["current"] == "tailor" and body["done"] is False and len(body["stages"]) == 2

    # unknown run -> empty, keep-polling snapshot (not a 404, so the client loop is simple)
    empty = client.get("/v1/runs/nope/progress", headers=h).json()
    assert empty["current"] == "" and empty["done"] is False


# ---- extension capture (POST /v1/tracker/capture) ---------------------------
def _no_enqueue(monkeypatch):
    """Stop the capture endpoint's `submit_tracker_match` from kicking off a REAL background match
    (which would hit the LLM). The match path itself is covered separately with mocks."""
    monkeypatch.setattr("apps.api.jobs.queue.InProcessQueue.submit_tracker_match",
                        lambda self, entry_id: None)


def test_capture_stores_jd_and_serves_screenshot(client, monkeypatch):
    """Capture creates the entry instantly, stores the raw JD in the DB (never in the response),
    writes the screenshot to the artifact store, and makes it servable via the runs endpoint."""
    _no_enqueue(monkeypatch)
    h = {"X-API-Key": "secret"}
    png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n-fake-image-bytes").decode()
    r = client.post("/v1/tracker/capture", headers=h, json={
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "raw_text": "We are hiring a Machine Learning Engineer. " * 6,
        "title": "AI Engineer",
        "screenshot": f"data:image/png;base64,{png_b64}",
    })
    assert r.status_code == 201
    entry = r.json()
    assert entry["title"] == "AI Engineer" and entry["run_id"]
    assert "captured_jd" not in entry                       # kept server-side, excluded from the API

    # the raw JD is persisted in the DB (small "keep ours" copy the reference discards)
    from resumaker.persistence import db
    stored = db.get_tracker(entry["id"])
    assert stored is not None and stored.captured_jd.startswith("We are hiring")

    # the screenshot is servable via the artifact endpoint (GCS would redirect; local streams)
    shot = client.get(f"/v1/runs/{entry['run_id']}/artifacts/screenshot.png", headers=h)
    assert shot.status_code == 200 and shot.content.startswith(b"\x89PNG")


def test_capture_jpeg_screenshot_served_as_jpg(client, monkeypatch):
    """A tall page is captured as JPEG; the backend stores + serves it as screenshot.jpg (not png)."""
    _no_enqueue(monkeypatch)
    h = {"X-API-Key": "secret"}
    jpg_b64 = base64.b64encode(b"\xff\xd8\xff-fake-jpeg-bytes").decode()
    r = client.post("/v1/tracker/capture", headers=h, json={
        "url": "https://jobs.ashbyhq.com/x/2", "raw_text": "Senior role JD body text. " * 8,
        "screenshot": f"data:image/jpeg;base64,{jpg_b64}"})
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    assert client.get(f"/v1/runs/{run_id}/artifacts/screenshot.jpg", headers=h).status_code == 200
    assert client.get(f"/v1/runs/{run_id}/artifacts/screenshot.png", headers=h).status_code == 404


def test_capture_without_screenshot_ok(client, monkeypatch):
    _no_enqueue(monkeypatch)
    h = {"X-API-Key": "secret"}
    r = client.post("/v1/tracker/capture", headers=h, json={
        "url": "https://jobs.lever.co/x/1", "raw_text": "A long enough job description body."})
    assert r.status_code == 201
    # no screenshot written -> the artifact 404s, but the entry still exists
    assert client.get(f"/v1/runs/{r.json()['run_id']}/artifacts/screenshot.png",
                      headers=h).status_code == 404


def test_capture_rejects_bad_input(client, monkeypatch):
    _no_enqueue(monkeypatch)
    h = {"X-API-Key": "secret"}
    base = {"url": "https://x.co/j/1", "raw_text": "valid jd text body here"}
    assert client.post("/v1/tracker/capture", headers=h,
                       json={**base, "raw_text": "   "}).status_code == 400          # empty
    assert client.post("/v1/tracker/capture", headers=h,
                       json={**base, "raw_text": "x" * 200_001}).status_code == 400   # oversized
    assert client.post("/v1/tracker/capture", headers=h,
                       json={**base, "url": "ftp://x/y"}).status_code == 400          # bad scheme
    assert client.post("/v1/tracker/capture", headers=h,
                       json={**base, "screenshot": "not-a-data-url"}).status_code == 400
    big = base64.b64encode(b"x" * (15 * 1024 * 1024 + 10)).decode()
    assert client.post("/v1/tracker/capture", headers=h,
                       json={**base, "screenshot": f"data:image/png;base64,{big}"}).status_code == 400


def test_capture_requires_token(client):
    assert client.post("/v1/tracker/capture",
                       json={"url": "https://x.co", "raw_text": "hello there jd body"}).status_code == 401


def test_match_uses_captured_jd_and_skips_scrape(client, monkeypatch):
    """When an entry carries a captured JD, the match structures THAT text and passes `job=` to the
    pipeline (so scrape is never called); the URL still rides along for report.json."""
    from resumaker.domain import JobPosting
    from resumaker.ingestion import tracker

    entry = tracker.capture(url="https://x.co/j/1", raw_text="Captured JD body. " * 12,
                            title="ML Engineer", run_id="cap-run-1")
    seen: dict = {}

    def fake_structure(raw, **kw):
        seen["structured"] = raw
        return JobPosting(title="ML Engineer", company="X Corp", raw_text=raw)

    def fake_run_pipeline(url=None, *, job=None, **kw):
        seen["url"], seen["job"] = url, job
        return type("R", (), {"job": job, "fit": None, "decision": None,
                              "sponsorship": None, "error": "", "out_dir": ""})()

    def boom_scrape(*a, **k):
        raise AssertionError("scrape must NOT run when a captured JD is present")

    monkeypatch.setattr("resumaker.stages.structure.structure_jd", fake_structure)
    monkeypatch.setattr("resumaker.pipeline.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr("resumaker.providers.scrape.scrape", boom_scrape)

    tracker.run_match_for(entry.id)
    assert seen["structured"].startswith("Captured JD body.")   # the captured text was structured
    assert seen["job"] is not None                              # job passed -> pipeline skips scrape
    assert seen["url"] == "https://x.co/j/1"                    # URL preserved for report.json
