"""RI ingestion tests: onboarding slug/ATS parsing (deterministic) + service dedupe
(fake source, isolated tmp DB). No network."""
from __future__ import annotations

import pytest

from resumaker.config import Settings
from resumaker.domain import BoardRef, Company
from resumaker.ingestion import onboard, service
from resumaker.providers.sources import available_sources
from resumaker.providers.sources.base import PostingStub


def test_sources_registered():
    assert set(available_sources()) == {
        "greenhouse", "lever", "ashby", "workday", "eightfold", "amazon", "oracle_cloud",
        "smartrecruiters", "mckinsey", "goldman", "phenom", "jibe", "radancy", "apple", "bytedance"}


def test_slug_candidates():
    c = onboard.slug_candidates("State Street")
    assert "statestreet" in c and "state-street" in c
    assert "state" not in c                               # bare first word dropped (anti-false-positive)
    c2 = onboard.slug_candidates("JPMC - Chase")
    assert "jpmc" in c2 and "chase" in c2                 # split on ' - '
    assert "bytedance" in onboard.slug_candidates("ByteDance/TikTok")
    assert all(len(s) >= 4 for s in c)                    # min-length guard


@pytest.mark.parametrize("html,source,token", [
    ('<a href="https://boards.greenhouse.io/databricks/jobs/1">', "greenhouse", "databricks"),
    ('<a href="https://jobs.lever.co/netflix">', "lever", "netflix"),
    ('<a href="https://jobs.ashbyhq.com/notion">', "ashby", "notion"),
])
def test_board_from_html(html, source, token):
    b = onboard.board_from_html(html)
    assert b and b.source == source and b.token == token


def test_board_from_html_workday():
    b = onboard.board_from_html('<iframe src="https://statestreet.wd1.myworkdayjobs.com/en-US/Global">')
    assert b and b.source == "workday" and b.token == "statestreet"
    assert b.extra["host"] == "statestreet.wd1.myworkdayjobs.com" and b.extra["site"] == "Global"


def test_board_from_html_none():
    assert onboard.board_from_html("<p>no ATS here</p>") is None


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    s = Settings(root_dir=tmp_path, data_dir=tmp_path / "data")
    for mod in ("resumaker.persistence.db", "resumaker.persistence.cache",
                "resumaker.config.settings"):
        monkeypatch.setattr(f"{mod}.get_settings", lambda: s)
    from resumaker.persistence import db
    db.init_db()
    return s


def test_service_dedupes_on_reingest(tmp_db, monkeypatch):
    stubs = [PostingStub(source="greenhouse", external_id="1", title="ML Engineer",
                         location="Boston", updated_at="2026-01-01"),
             PostingStub(source="greenhouse", external_id="2", title="Data Scientist",
                         location="NYC", updated_at="2026-01-02")]

    class Fake:
        source = "greenhouse"
        def list_postings(self, token, **kw):
            return stubs

    monkeypatch.setattr(service, "get_source", lambda name: Fake())
    company = Company(name="Acme", boards=[BoardRef(source="greenhouse", token="acme")])

    r1 = service.ingest_company(company)
    assert r1.new == 2 and r1.unchanged == 0 and len(r1.new_jobs) == 2
    assert r1.new_jobs[0].posted_at == "2026-01-01"        # posted date captured

    r2 = service.ingest_company(company)                    # re-ingest, nothing changed
    assert r2.new == 0 and r2.unchanged == 2

    stubs[0].title = "Senior ML Engineer"                   # edited posting -> changed
    r3 = service.ingest_company(company)
    assert r3.new == 1 and r3.unchanged == 1


@pytest.mark.parametrize("loc,is_us", [
    ("Boston, MA", True), ("New York, NY", True), ("Chicago, IL", True),
    ("Remote - US", True), ("United States", True), ("San Francisco, California", True),
    ("Dublin, CA", True),                         # Dublin, California (US abbr wins)
    ("", True),                                    # unknown -> keep
    ("Austin", True),                              # bare US city (no comma) -> keep
    ("Remote", True),                              # remote -> keep
    ("Bengaluru, India", False), ("Krakow, Poland", False), ("London, United Kingdom", False),
    ("Toronto, ON, Canada", False), ("Gdansk, Poland", False), ("Singapore", False),
    ("Bratislava, Bratislava", False),             # 'City, Region' no US signal -> foreign
    ("Cambridge, England", False),
])
def test_is_us_location(loc, is_us):
    assert service.is_us_location(loc) is is_us


@pytest.mark.parametrize("title,is_tech", [
    ("Senior Machine Learning Engineer", True), ("Software Engineer II", True),
    ("Data Scientist", True), ("Data Engineer, Platform", True), ("AI Engineer", True),
    ("Site Reliability Engineer", True), ("Backend Developer", True),
    ("Cloud Solutions Architect", True), ("SDET", True),
    ("Sales Engineer", False),                 # non-tech marker overrides "engineer"
    ("Technical Recruiter", False), ("Financial Analyst", False),
    ("Registered Nurse", False), ("Warehouse Associate", False),
    ("Marketing Manager", False), ("Store Manager", False),
    ("Product Designer", False),               # ambiguous -> default drop (no tech marker)
])
def test_is_tech_role(title, is_tech):
    assert service.is_tech_role(title) is is_tech


def test_preference_filter(monkeypatch):
    monkeypatch.setattr("resumaker.enrichment.preferences",
                        lambda: {"target_roles": ["engineer"], "avoid_roles": ["sales"]})
    assert service.matches_preferences("Machine Learning Engineer") is True
    assert service.matches_preferences("Sales Engineer") is False   # avoid wins
    assert service.matches_preferences("Product Manager") is False  # no target kw
