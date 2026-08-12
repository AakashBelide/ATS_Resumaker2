"""RI ingestion tests: onboarding slug/ATS parsing (deterministic) + service dedupe
(fake source, isolated tmp DB). No network."""
from __future__ import annotations

import json

import pytest

from resumaker.config import Settings
from resumaker.domain import BoardRef, Company
from resumaker.ingestion import onboard, service
from resumaker.providers.sources import available_sources
from resumaker.providers.sources.base import PostingStub


def test_sources_registered():
    assert set(available_sources()) == {
        "greenhouse", "lever", "ashby", "workday", "eightfold", "amazon", "oracle_cloud",
        "smartrecruiters", "mckinsey", "goldman", "phenom", "jibe", "radancy", "apple",
        "bytedance", "dassault", "microsoft", "google", "meta", "tesla", "pcsx", "paradox",
        "ibm", "icims", "wayfair", "algolia", "recruitee"}


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


def test_discovery_filters_and_facets(tmp_db, monkeypatch):
    from resumaker.domain import JobRecord
    from resumaker.ingestion import DiscoveryFilters, discover
    from resumaker.persistence import db
    rows = [
        ("greenhouse", "1", "Machine Learning Engineer", "Anthropic", "San Francisco, CA"),
        ("greenhouse", "2", "Data Engineer", "Anthropic", "New York, NY"),
        ("ashby", "3", "Security Engineer", "OpenAI", "Remote, US"),
        ("workday", "4", "Staff Software Engineer", "NVIDIA", "Santa Clara, CA"),
    ]
    for src, ext, title, co, loc in rows:
        db.upsert_job(JobRecord(source=src, external_id=ext, title=title, company=co,
                                location=loc, content_hash=ext))

    # unfiltered
    r = discover(DiscoveryFilters())
    assert r.total == 4 and len(r.jobs) == 4
    assert r.facets["companies"]["Anthropic"] == 2

    # company filter
    assert discover(DiscoveryFilters(company=["Anthropic"])).total == 2
    # source filter
    assert discover(DiscoveryFilters(source="ashby")).total == 1
    # location substring
    assert discover(DiscoveryFilters(location="ca")).total == 2   # SF + Santa Clara
    # keyword matches title OR company
    assert discover(DiscoveryFilters(keyword="engineer")).total == 4
    assert discover(DiscoveryFilters(keyword="data")).total == 1
    assert discover(DiscoveryFilters(keyword="nvidia")).total == 1   # company match
    # multi-select company / level
    assert discover(DiscoveryFilters(company=["Anthropic", "OpenAI"])).total == 3
    assert discover(DiscoveryFilters(level=["senior", "staff"])).total == 1  # 'Staff Software Engineer'
    # pagination
    assert len(discover(DiscoveryFilters(limit=2)).jobs) == 2


def test_tracker_add_runs_match_and_lifecycle(tmp_db, monkeypatch):
    from resumaker.domain import JobRecord
    from resumaker.ingestion import tracker
    from resumaker.persistence import db

    jid, _ = db.upsert_job(JobRecord(source="greenhouse", external_id="1",
                                     title="ML Engineer", company="Anthropic",
                                     location="SF, CA", url="https://x/jobs/1", content_hash="1"))

    # stub the match pipeline (no network/LLM) with a PipelineResult-like object
    from types import SimpleNamespace
    res = SimpleNamespace(
        error="",
        job=SimpleNamespace(company="Anthropic", title="Machine Learning Engineer"),
        fit=SimpleNamespace(final_0_100=78.0),
        decision=SimpleNamespace(recommend_apply=True),
        sponsorship={"verdict": "likely"},
        out_dir="/tmp/outputs/anthropic-mle")
    monkeypatch.setattr("resumaker.pipeline.run_pipeline", lambda **kw: res)

    e = tracker.add(job_id=jid)
    assert e.stage == "interested" and e.fit_0_100 == 78.0 and e.recommend_apply is True
    assert e.sponsorship == "likely" and e.run_id == "anthropic-mle"
    assert e.title == "Machine Learning Engineer"      # structured JD title preferred

    # lifecycle
    assert tracker.set_stage(e.id, "applied").stage == "applied"
    with pytest.raises(tracker.TrackerError):
        tracker.set_stage(e.id, "bogus")
    tracker.set_notes(e.id, "referred by X")
    assert db.get_tracker(e.id).notes == "referred by X"

    # re-add refreshes match but preserves stage + notes (keyed on url)
    e2 = tracker.add(job_id=jid)
    assert e2.id == e.id and e2.stage == "applied" and e2.notes == "referred by X"

    assert len(tracker.list_tracked()) == 1
    assert len(tracker.list_tracked(stage="applied")) == 1
    assert len(tracker.list_tracked(stage="interested")) == 0


def test_tracker_add_requires_target(tmp_db):
    from resumaker.ingestion import tracker
    with pytest.raises(tracker.TrackerError):
        tracker.add(run_match=False)


def test_tracker_match_failure_sets_error_then_retry_clears(tmp_db, monkeypatch):
    """A failed match records `match_error` (not an eternal 'matching…'); a later successful
    rematch clears it and fills in fit/decision."""
    from types import SimpleNamespace

    from resumaker.domain import JobRecord
    from resumaker.ingestion import tracker
    from resumaker.persistence import db

    jid, _ = db.upsert_job(JobRecord(source="oracle_cloud", external_id="9",
                                     title="Data Engineer", company="JPMC",
                                     location="TX", url="https://x/job/9", content_hash="9"))

    failed = SimpleNamespace(error="RuntimeError: all extraction passes failed",
                             job=None, fit=None, decision=None, sponsorship=None, out_dir="")
    monkeypatch.setattr("resumaker.pipeline.run_pipeline", lambda **kw: failed)
    e = tracker.add(job_id=jid)
    assert e.fit_0_100 is None and e.match_error and "extraction" in e.match_error

    # retry with a now-succeeding pipeline clears the error and populates the match
    ok = SimpleNamespace(error="",
                         job=SimpleNamespace(company="JPMorgan Chase", title="Data Engineer III"),
                         fit=SimpleNamespace(final_0_100=44.1),
                         decision=SimpleNamespace(recommend_apply=False),
                         sponsorship={"verdict": "likely"}, out_dir="/tmp/outputs/jpmc-de")
    monkeypatch.setattr("resumaker.pipeline.run_pipeline", lambda **kw: ok)
    cleared = tracker.clear_match_error(e.id)
    assert cleared.match_error is None
    tracker.run_match_for(e.id)
    got = db.get_tracker(e.id)
    assert got.match_error is None and got.fit_0_100 == 44.1 and got.run_id == "jpmc-de"


def test_title_matches_include_exclude():
    """Shared title gate: contains ANY include word AND NONE of the exclude words."""
    from resumaker.ingestion.service import title_matches
    # want AI, drop Java/Manager
    assert title_matches("AI Engineer", include=["ai"], exclude=["java", "manager"])
    assert not title_matches("Java AI Engineer", include=["ai"], exclude=["java"])   # excluded
    assert not title_matches("Engineering Manager", include=["ai"], exclude=["manager"])
    assert not title_matches("Backend Engineer", include=["ai"], exclude=[])         # missing include
    assert title_matches("Backend Engineer", include=[], exclude=["java"])           # no include req
    assert title_matches("ML Engineer", include=["ai", "ml"], exclude=[])            # ANY include


def test_discovery_title_filter(tmp_db, monkeypatch):
    from resumaker.domain import JobRecord
    from resumaker.ingestion import DiscoveryFilters, discover
    from resumaker.persistence import db

    for i, title in enumerate(["AI Engineer", "Java AI Engineer", "ML Engineer", "Data Analyst"]):
        db.upsert_job(JobRecord(source="greenhouse", external_id=str(i), title=title,
                                company="Acme", location="Boston, MA", content_hash=str(i)))
    res = discover(DiscoveryFilters(title_include=["engineer"], title_exclude=["java"], limit=50))
    titles = {j.title for j in res.jobs}
    assert titles == {"AI Engineer", "ML Engineer"}          # engineer, not java, not analyst


def test_mailer_filter_narrows_pending(tmp_db):
    """The email digest applies the owner's mailer title filter (include/exclude) on top of the
    on-target gate; default empty = no change."""
    from resumaker.domain import JobRecord
    from resumaker.ingestion import notify
    from resumaker.persistence import db, profile

    for i, t in enumerate(["AI Engineer", "Java Engineer"]):
        db.upsert_job(JobRecord(source="greenhouse", external_id=str(i), title=t,
                                company="Acme", content_hash=str(i)))
    jobs = db.list_jobs()
    assert {j.title for j in notify.pending(jobs)} == {"AI Engineer", "Java Engineer"}  # no filter

    profile.save_mailer_filter({"include": ["ai"], "exclude": ["java"]})
    assert {j.title for j in notify.pending(jobs)} == {"AI Engineer"}   # filtered


def test_actions_agent_runner_dispatch_poll_artifact(monkeypatch):
    """ActionsAgentRunner: dispatch the workflow, find the run by run-name, then download the
    contract artifact - all mocked (no GitHub calls). Fits the synchronous resolve() seam."""
    import io
    import json
    import zipfile

    from resumaker.config import get_settings
    from resumaker.onboarding import agent_runner as ar

    for k, v in {"RESUMAKER_ONBOARD_AGENT_ENABLED": "true", "RESUMAKER_ONBOARD_RUNNER": "actions",
                 "RESUMAKER_GITHUB_REPO": "me/repo", "RESUMAKER_GITHUB_TOKEN": "ghp_x"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("time.sleep", lambda *_: None)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("contract.json", json.dumps(
            {"status": "resolved", "board": {"source": "greenhouse", "token": "acme"},
             "cost_usd": 0.1, "turns": 3}))
    zip_bytes = buf.getvalue()

    class Resp:
        def __init__(self, js=None, content=b""): self._js, self.content = js, content
        def raise_for_status(self): pass
        def json(self): return self._js

    class FakeHTTP:
        def post(self, url, json=None): return Resp()  # dispatch -> 204
        def get(self, url, params=None, follow_redirects=False):
            if url.endswith("/actions/runs"):
                return Resp({"workflow_runs": [
                    {"name": "onboard-r1", "id": 99, "status": "completed", "conclusion": "success"}]})
            if url.endswith("/artifacts"):
                return Resp({"artifacts": [{"name": "contract-r1", "archive_download_url": "dl"}]})
            return Resp(content=zip_bytes)  # the artifact zip download

    runner = ar.get_agent_runner()
    assert isinstance(runner, ar.ActionsAgentRunner)   # config selected the Actions runner
    runner._http = FakeHTTP()
    runner._poll_s = 0
    got = runner.resolve("Acme", None, run_id="r1", on_event=lambda *a: None)
    assert got["status"] == "resolved" and got["board"]["source"] == "greenhouse"
    assert got["turns"] == 3
    get_settings.cache_clear()


def test_agent_runner_actions_requires_repo_and_token(monkeypatch):
    """Without github creds, actions mode falls back to Null (never crashes onboarding)."""
    from resumaker.config import get_settings
    from resumaker.onboarding import agent_runner as ar

    monkeypatch.setenv("RESUMAKER_ONBOARD_AGENT_ENABLED", "true")
    monkeypatch.setenv("RESUMAKER_ONBOARD_RUNNER", "actions")  # but no repo/token set
    get_settings.cache_clear()
    assert isinstance(ar.get_agent_runner(), ar.NullAgentRunner)
    get_settings.cache_clear()


def test_oracle_cloud_scraper(monkeypatch):
    """The oracle_cloud handler recognizes CE careers URLs and pulls the JD from the public
    requisition-detail JSON API (the JS page's own source), not the empty HTML shell."""
    import httpx

    from resumaker.providers.scrape import scraper

    detail = {"Title": "Data Engineer III", "PrimaryLocation": "Houston, TX",
              "ExternalDescriptionStr": "<p>Build <b>data</b> pipelines.</p>",
              "ExternalResponsibilitiesStr": "<ul><li>Own ETL</li></ul>"}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return detail

    seen = {}

    def fake_get(url, **kw):
        seen["url"] = url
        return _Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    url = "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210759920"
    r = scraper._oracle_cloud(url)
    assert r is not None and r.source_type == "oracle_cloud"
    assert r.title == "Data Engineer III" and r.company == "jpmc"
    low = r.raw_text.lower()
    assert "pipelines" in low and "own etl" in low   # both JD fields stitched + de-HTML'd
    assert "recruitingCEJobRequisitionDetails/210759920" in seen["url"]
    # a non-oracle URL is not claimed by this handler
    assert scraper._oracle_cloud("https://boards.greenhouse.io/acme/jobs/1") is None


def test_dashboard_stats(tmp_db):
    from resumaker.analytics import dashboard_stats
    from resumaker.domain import JobRecord, TrackerEntry
    from resumaker.persistence import db
    for ext, co, src in [("1", "Anthropic", "greenhouse"), ("2", "Anthropic", "greenhouse"),
                         ("3", "OpenAI", "ashby")]:
        db.upsert_job(JobRecord(source=src, external_id=ext, title="ML Engineer",
                                company=co, location="SF, CA", url=f"u{ext}", content_hash=ext))
    db.upsert_tracker(TrackerEntry(url="u1", company="Anthropic", stage="applied"))
    db.upsert_tracker(TrackerEntry(url="u3", company="OpenAI", stage="interested"))
    s = dashboard_stats()
    assert s["watchlist"]["jobs"] == 3 and s["watchlist"]["tracked"] == 2
    assert s["jobs_by_company"]["Anthropic"] == 2
    assert s["jobs_by_source"]["greenhouse"] == 2 and s["jobs_by_source"]["ashby"] == 1
    assert s["tracker_funnel"] == {"applied": 1, "interested": 1}
    assert sum(d["count"] for d in s["new_listings_daily"]) == 3   # all first-seen today


def test_enrichment_proposals(tmp_path, monkeypatch):
    from resumaker.domain import TrackerEntry
    from resumaker.enrichment import proposals as pr
    monkeypatch.setattr(pr, "get_settings",
                        lambda: type("S", (), {"output_root": tmp_path})())
    monkeypatch.setattr(pr.db, "list_tracker",
                        lambda: [TrackerEntry(id=1, url="u", run_id="acme-mle", company="Acme")])
    monkeypatch.setattr(pr.profile, "all_skills", lambda: {"Python"})
    d = tmp_path / "acme-mle"
    d.mkdir()
    (d / "report.json").write_text(json.dumps({"gap": {"items": [
        {"requirement": "Kubernetes orchestration", "status": "supportedByResume",
         "evidence": "ran k8s in prod"},
        {"requirement": "Rust systems programming", "status": "gap"},
        {"requirement": "Python scripting", "status": "supportedByResume"},  # already listed
        {"requirement": "Go", "status": "existing"},                          # not a signal
    ]}}))
    out = pr.propose_from_tracker()
    have = [p.requirement for p in out["have_but_unlisted"]]
    gaps = [p.requirement for p in out["recurring_gaps"]]
    assert "Kubernetes orchestration" in have
    assert "Python scripting" not in have          # a listed skill appears -> skipped
    assert gaps == ["Rust systems programming"]
    assert out["have_but_unlisted"][0].companies == ["Acme"]


def test_discovery_on_target_gate(tmp_db, monkeypatch):
    from resumaker.domain import JobRecord
    from resumaker.ingestion import DiscoveryFilters, discover
    from resumaker.persistence import db
    monkeypatch.setattr("resumaker.enrichment.preferences",
                        lambda: {"target_roles": ["engineer"], "avoid_roles": ["security"]})
    for ext, title in [("1", "ML Engineer"), ("2", "Security Engineer"), ("3", "Recruiter")]:
        db.upsert_job(JobRecord(source="greenhouse", external_id=ext, title=title,
                                company="Acme", location="Boston, MA", content_hash=ext))
    r = discover(DiscoveryFilters(on_target=True))
    assert {j.title for j in r.jobs} == {"ML Engineer"}   # engineer target, security avoided
    assert r.total == 1


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
    ("Bangalore, In", False), ("Hyderabad, In", False),  # 'In' == India, not Indiana
    ("Indianapolis, IN", True),                    # no foreign marker -> Indiana abbr wins
    ("Atlanta, Boston", True), ("Boston, Chicago", True),  # multi US city, no state token
])
def test_is_us_location(loc, is_us):
    assert service.is_us_location(loc) is is_us


@pytest.mark.parametrize("loc,states", [
    ("San Jose, CA", ["CA"]),
    ("San Francisco, CA | New York City, NY", ["CA", "NY"]),
    ("US-CA-Menlo Park", ["CA"]),
    ("Austin, Texas", ["TX"]),
    ("2 Locations", []), ("Remote - USA", []), ("", []),  # unresolved -> OTHER bucket
    ("Bangalore, In", ["IN"]),                     # note: kept only for parity; dropped at ingest
    ("Atlanta, Boston", ["GA", "MA"]),             # multi-city -> both states via city map
])
def test_us_states_of(loc, states):
    assert service.us_states_of(loc) == states


@pytest.mark.parametrize("title,level", [
    ("Machine Learning Intern", "intern"), ("Data Science Co-op", "intern"),
    ("Engineering Manager", "manager"), ("Senior Manager, Data Science", "manager"),
    ("Staff Software Engineer", "staff"), ("Principal AI Engineer", "staff"),
    ("Senior Data Engineer", "senior"), ("Lead ML Engineer", "senior"),
    ("New Grad Software Engineer", "junior"), ("Junior Developer", "junior"),
    ("Data Scientist", "mid"), ("Software Engineer", "mid"),
    ("International Growth Analyst", "mid"),        # 'intern' must not fire on 'international'
])
def test_title_level(title, level):
    assert service.title_level(title) == level


def test_mckinsey_job_url():
    from resumaker.providers.sources.mckinsey import mckinsey_job_url
    # Best-effort fallback slug rule (matches live `friendlyURL` 100/100): lowercase, keep
    # ASCII hyphen-minus, strip every other non-alnum incl. en/em dashes, collapse + trim.
    # en-dash '–' is stripped -> NO hyphen before quantumblack
    assert mckinsey_job_url("Knowledge Graph Data Engineer – QuantumBlack, AI by McKinsey", "110946") == (
        "https://www.mckinsey.com/careers/search-jobs/jobs/"
        "knowledgegraphdataengineerquantumblackaibymckinsey-110946")
    # ASCII hyphen '-' is kept -> hyphen survives before quantumblack
    assert mckinsey_job_url("Senior Knowledge Graph Data Engineer - QuantumBlack, AI by McKinsey", "110947") == (
        "https://www.mckinsey.com/careers/search-jobs/jobs/"
        "seniorknowledgegraphdataengineer-quantumblackaibymckinsey-110947")
    # no title -> bare id form (last resort)
    assert mckinsey_job_url("", "110946") == "https://www.mckinsey.com/careers/search-jobs/jobs/110946"


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
    ("Data Consultant", True), ("Analytics Consultant", True),  # tech-qualified consulting kept
    ("Statistician", True), ("Applied Scientist", True), ("Research Scientist", True),
    ("Financial Analyst", False), ("Management Consultant", False),  # pure-business still dropped
])
def test_is_tech_role(title, is_tech):
    assert service.is_tech_role(title) is is_tech


def test_preference_filter(monkeypatch):
    monkeypatch.setattr("resumaker.enrichment.preferences",
                        lambda: {"target_roles": ["engineer"], "avoid_roles": ["sales"]})
    assert service.matches_preferences("Machine Learning Engineer") is True
    assert service.matches_preferences("Sales Engineer") is False   # avoid wins
    assert service.matches_preferences("Product Manager") is False  # no target kw


def test_notify_digest_and_dedupe(tmp_db):
    from resumaker.domain import JobRecord
    from resumaker.ingestion import notify
    from resumaker.persistence import db
    jobs = [
        JobRecord(source="greenhouse", external_id="1", title="Machine Learning Engineer",
                  company="Acme", location="SF, CA", url="https://x/1", content_hash="1",
                  comp="$200K – $250K"),
        JobRecord(source="ashby", external_id="2", title="Data Engineer", company="Beta",
                  location="NYC", url="https://x/2", content_hash="2"),
        JobRecord(source="greenhouse", external_id="3", title="Office Manager", company="Acme",
                  location="SF", url="https://x/3", content_hash="3"),   # off-target -> excluded
    ]
    # pending = on-target (net match) AND not-yet-emailed
    p = notify.pending(jobs)
    assert {j.external_id for j in p} == {"1", "2"}
    subject, html_body, text_body = notify.build_digest(p)
    assert "2 new" in subject
    assert "Machine Learning Engineer" in html_body and "$200K – $250K" in html_body
    assert "https://x/1" in text_body
    # dry-run counts without needing email config, and does NOT mark
    assert notify.email_new(jobs, dry_run=True) == 2
    assert len(notify.pending(jobs)) == 2
    # once marked, they never re-notify
    db.mark_notified(p)
    assert notify.pending(jobs) == []


def test_matches_preferences_broad_net(monkeypatch):
    # avoid labels carry '(pure)' qualifiers in the real profile - must still block the role
    monkeypatch.setattr("resumaker.enrichment.preferences", lambda: {
        "target_roles": ["AI Engineer", "Machine Learning Engineer", "Data Scientist"],
        "avoid_roles": ["Security Engineer", "Frontend Engineer (pure)",
                        "Site Reliability Engineer (pure infra)"]})
    for t in ["Software Development Engineer, ECS", "Applied Scientist", "ML Engineer",
              "Data Analyst", "Enterprise Systems Architecture", "Senior Data Scientist"]:
        assert service.matches_preferences(t) is True, t
    for t in ["Security Engineer", "Frontend Engineer", "Senior Site Reliability Engineer",
              "Data Center Engineering Operations Technician", "IT Support Engineer",
              "Email Marketing Manager"]:
        assert service.matches_preferences(t) is False, t


def test_google_parse_response():
    from resumaker.providers.sources.google import parse_response
    # ds:1 blob: data = [ [job...], null, total, page_size ]. Job is a positional array.
    job = ["87598862385980102", "Staff Software Engineer", "https://apply", ["r"], ["q"],
           "co/path", None, "Google", "en-US",
           [["Sunnyvale, CA, USA", [], "Sunnyvale", "94089", "CA", "US"]],
           ["desc"], [2, 3], [1782808699, 0], [1782808699, 0], [1782808699, 0]]
    html = ("<script>AF_initDataCallback({key: 'ds:1', hash: '1', data:"
            + json.dumps([[job], None, 1575, 20]) + ", sideChannel: {}});</script>")
    stubs, total = parse_response(html)
    assert total == 1575 and len(stubs) == 1
    assert stubs[0].external_id == "87598862385980102"
    assert stubs[0].title == "Staff Software Engineer"
    assert stubs[0].location == "Sunnyvale, CA, USA"
    assert stubs[0].updated_at.startswith("2026")
    assert parse_response("<html>no ds:1 here</html>") == ([], 0)


def test_tesla_parse_response():
    from resumaker.providers.sources.tesla import parse_response
    body = {"lookup": {"locations": {"401022": "Palo Alto, California",
                                     "500": "Toronto, Ontario"}},
            "listings": [{"id": "224501", "t": "AI Engineer, Optimus", "dp": "3", "l": "401022"},
                         {"id": "9", "t": "Foo", "dp": "1", "l": "500"}]}
    stubs = parse_response(body)
    assert len(stubs) == 2
    assert stubs[0].external_id == "224501" and stubs[0].title == "AI Engineer, Optimus"
    assert stubs[0].location == "Palo Alto, California"
    assert stubs[0].url.endswith("/job/224501")


def test_pcsx_parse_response():
    from resumaker.providers.sources.pcsx import parse_response
    body = {"data": {"count": 2, "positions": [
        {"id": 446717683325, "displayJobId": "3088561", "name": "ML Engineer",
         "standardizedLocations": ["San Diego, CA, US"],
         "locations": ["San Diego, California, USA"], "postedTs": 1774569600,
         "positionUrl": "/careers/job/446717683325"}]}}
    stubs, total = parse_response(body)
    assert total == 2 and len(stubs) == 1
    assert stubs[0].external_id == "446717683325" and stubs[0].title == "ML Engineer"
    assert stubs[0].location == "San Diego, CA, US"       # standardized (US suffix) preferred
    assert stubs[0].updated_at.startswith("2026")
    assert stubs[0].url == "https://app.eightfold.ai/careers/job/446717683325"


def test_meta_handshake_and_parse():
    from resumaker.providers.sources.meta import (
        extract_doc_id,
        find_bundle_urls,
        parse_response,
        scrape_lsd,
    )
    page = ('...["LSD",[],{"token":"AbC_123"}]... '
            '"https://static.xx.fbcdn.net/rsrc.php/v3/yb/abc.js?_nc_x=1" '
            'other "https://z.fbcdn.net/rsrc.php/def.js"')
    assert scrape_lsd(page) == "AbC_123"
    bundles = find_bundle_urls(page)
    assert bundles[0].endswith("abc.js?_nc_x=1") and len(bundles) == 2
    # doc_id lives in a Relay operation module inside a JS bundle, not the page HTML:
    js = ('__d("CareersJobSearchResultsDataQuery_candidate_portalRelayOperation",[],'
          '(function(t,n,r,o,a,i){a.exports="27506805582236862"}),null);')
    assert extract_doc_id(js) == "27506805582236862"
    assert extract_doc_id("no operation module here") == ""
    body = {"data": {"job_search_with_featured_jobs": {
        "all_jobs": [{"id": "111", "title": "SWE",
                      "locations": ["Menlo Park, CA", "Seattle, WA"]}],
        "featured_jobs": [{"id": "222", "title": "MLE", "locations": ["Remote, US"]}]}}}
    stubs = parse_response(body)
    assert {s.external_id for s in stubs} == {"111", "222"}
    assert stubs[0].location == "Menlo Park, CA, Seattle, WA"
    assert stubs[0].url == "https://www.metacareers.com/jobs/111/"


def test_paradox_parse_response():
    from resumaker.providers.sources.paradox import parse_response
    body = {"totalJob": 2363, "jobs": [
        {"uniqueID": "PDX_FEC_ABC", "reference": "P25-354057-1", "title": "Software Engineer",
         "applyURL": "https://fedex.paradox.ai/co/X/Job?job_id=P25-354057-1",
         "locations": [{"city": "Memphis", "stateAbbr": "TN", "countryAbbr": "US"}],
         "customFields": [{"cfKey": "cf_effective_date", "value": "2026-08-07"}]}]}
    stubs, total = parse_response(body)
    assert total == 2363 and len(stubs) == 1
    assert stubs[0].external_id == "PDX_FEC_ABC" and stubs[0].title == "Software Engineer"
    assert stubs[0].location == "Memphis, TN, US" and stubs[0].updated_at == "2026-08-07"


def test_ibm_parse_response():
    from resumaker.providers.sources.ibm import parse_response
    body = {"hits": {"total": {"value": 140, "relation": "eq"}, "hits": [
        {"_id": "sha", "_source": {"id": "sha", "title": "Senior Software Engineer",
         "url": "https://careers.ibm.com/careers/JobDetail?jobId=127642",
         "field_keyword_05": "United States", "field_keyword_19": "Austin, US"}}]}}
    stubs, total = parse_response(body)
    assert total == 140 and len(stubs) == 1
    assert stubs[0].external_id == "127642"            # numeric jobId lifted from the url
    assert stubs[0].title == "Senior Software Engineer" and stubs[0].location == "Austin, US"


def test_icims_parse_page():
    from resumaker.providers.sources.icims import parse_page, total_pages
    row = ('<div class="row"><a class="iCIMS_Anchor" '
           'href="https://careers-suffolkconstruction.icims.com/jobs/9597/general-superintendent/job?x=1" '
           'title="9597 - General Superintendent"><h3>General Superintendent</h3></a>'
           '<span class="glyphicons-map-marker"></span><dd>US-TX-Austin | US-TX-Wilmer</dd></div>')
    html = f'<span>Page 1 of 15</span>{row}'
    assert total_pages(html) == 15
    stubs = parse_page(html)
    assert len(stubs) == 1
    assert stubs[0].external_id == "9597" and stubs[0].title == "General Superintendent"
    assert stubs[0].location == "Austin, TX, US"        # US-TX-Austin normalized, first of pipe list
    assert stubs[0].url.endswith("/general-superintendent/job")


def test_wayfair_parse_response():
    from resumaker.providers.sources.wayfair import parse_response
    body = {"jobListData": [
        {"id": 60428, "eid": "9812", "title": "Software Engineer",
         "location": {"name": "Boston, MA", "city": "Boston", "state": "MA",
                      "country": "US", "countryId": 1},
         "applyLink": "https://wayfair.avature.net/en_US/careers?folderId=9812",
         "lastUpdatedDate": "2026-05-05T12:47:10.933000"}]}
    stubs = parse_response(body)
    assert len(stubs) == 1
    assert stubs[0].external_id == "60428" and stubs[0].title == "Software Engineer"
    assert stubs[0].location == "Boston, MA"
    assert "avature.net" in stubs[0].url and stubs[0].updated_at.startswith("2026")


def test_microsoft_parse_response():
    from resumaker.providers.sources.microsoft import parse_response
    body = {"operationResult": {"result": {"totalJobs": 2, "jobs": [
        {"jobId": "1846000", "title": "Senior Software Engineer",
         "properties": {"locations": ["Redmond, Washington, United States"],
                        "postingDate": "2026-08-08T00:00:00Z"}},
        {"jobId": "1846001", "title": "Data Scientist",
         "properties": {"primaryLocation": "Remote, US", "postingDate": "2026-08-07"}},
    ]}}}
    stubs, total = parse_response(body)
    assert total == 2 and len(stubs) == 2
    assert stubs[0].external_id == "1846000" and "Redmond" in stubs[0].location
    assert stubs[0].title == "Senior Software Engineer" and stubs[0].updated_at.startswith("2026")
    assert stubs[1].location == "Remote, US"
