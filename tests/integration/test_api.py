"""R5 API tests via FastAPI TestClient. No real pipeline runs (manager.start is mocked);
an isolated tmp data dir keeps SQLite + PII off the real filesystem."""
from __future__ import annotations

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
    monkeypatch.setattr("apps.api.routers.runs.manager.start", lambda url, **k: "run123")
    r = client.post("/v1/runs", headers={"X-API-Key": "secret"},
                    json={"url": "https://boards.greenhouse.io/x/jobs/1"})
    assert r.status_code == 202 and r.json() == {"run_id": "run123", "status": "running"}


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


def test_worker_endpoints_require_token(client):
    assert client.post("/v1/worker/ingest-tick", json={}).status_code == 401
    assert client.post("/v1/worker/run-pipeline", json={"url": "x"}).status_code == 401


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
