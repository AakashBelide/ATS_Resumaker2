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
        "ibm", "icims", "wayfair"}


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
