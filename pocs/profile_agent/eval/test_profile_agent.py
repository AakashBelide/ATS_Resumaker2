"""Deterministic tests for the profile agent - no live LLM.

Covers the load-bearing, non-LLM logic: slash-command parsing, the anti-fabrication quote gate,
apply/undo through a temp profile, the intake thin-spot detector, and a full enhance turn driven by
a fake LLM (so the turn loop, proposal filtering, confirm->apply path are exercised end-to-end).
"""
from __future__ import annotations

import json

import pytest
from pocs.profile_agent import agent, enhance, intake, store
from pocs.profile_agent.store import Proposal


# ---- slash commands + message classification ------------------------------
@pytest.mark.parametrize("msg,cmd", [
    ("/done", "/done"), ("  /GENERATE now ", "/generate"), ("/stop", "/stop"),
    ("hello", None), ("/nope", "__unknown__"),
])
def test_parse_slash(msg, cmd):
    assert agent.parse_slash(msg)[0] == cmd


@pytest.mark.parametrize("msg,ok", [("yes", True), ("Apply.", True), ("go ahead", True),
                                    ("maybe later", False), ("no", False)])
def test_is_affirmative(msg, ok):
    assert agent.is_affirmative(msg) is ok


@pytest.mark.parametrize("msg,expected", [
    ("yes", (True, "")),
    ("Sure!", (True, "")),
    ("yes, I built it from Jan to Aug 2026", (True, "I built it from Jan to Aug 2026")),
    ("yeah and it uses Kafka", (True, "it uses Kafka")),
    ("yes but actually put it under CurateAI", (False, "")),   # redirect, not a clean confirm
    ("yes, no wait", (False, "")),
    ("yesterday I shipped it", (False, "")),                    # not a confirmation at all
    ("maybe later", (False, "")),
])
def test_split_affirmative(msg, expected):
    assert agent.split_affirmative(msg) == expected


# ---- anti-fabrication: the quote must come from the user ------------------
def test_quote_supported_gate():
    user = "At Granite I stood up a Qdrant vector store and cut retrieval latency about 40%."
    assert agent.quote_supported("stood up a Qdrant vector store", user)
    assert agent.quote_supported("cut retrieval latency about 40%", user)
    assert not agent.quote_supported("led a team of 30 engineers", user)   # never said -> rejected
    assert not agent.quote_supported("", user)


def test_to_proposals_drops_ungrounded():
    user = "I used Kafka on the fraud stream at Bajaj."
    raw = [
        {"kind": "add_skill", "path": ["skills", "Big Data & Data Engineering"], "value": "Kafka",
         "source_quote": "I used Kafka on the fraud stream", "preview": "add Kafka"},
        {"kind": "add_skill", "path": ["skills", "x"], "value": "Spark",
         "source_quote": "I built Spark pipelines"},   # not in the user's message -> dropped
    ]
    accepted, rejected = agent.to_proposals(raw, user)
    assert [p.value for p in accepted] == ["Kafka"]
    assert len(rejected) == 1


# ---- apply / undo against a temp profile ---------------------------------
@pytest.fixture
def temp_profile(tmp_path, monkeypatch):
    prof = {"skills": {"Big Data & Data Engineering": ["Spark"]},
            "experience": [{"title": "MLE", "organization": "Granite",
                            "bullets": [{"text": "Built NL2SQL", "metrics": [], "skills_used": []}]}],
            "summary": ""}
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(prof))
    # keep the audit log out of the repo during tests; apply_proposal reads/writes `p` directly.
    from resumaker.enrichment import manager
    monkeypatch.setattr(manager, "record_enrichment", lambda *a, **k: {})
    return p


def test_apply_and_undo_skill(temp_profile):
    st = store.new_run("enhance")
    prop = Proposal(kind="add_skill", path=["skills", "Big Data & Data Engineering"], value="Kafka",
                    source_quote="used Kafka", preview="add Kafka")
    st.pending = [prop.__dict__]
    n = agent.apply_pending(st, profile_path=temp_profile)
    assert n == 1
    saved = json.loads(temp_profile.read_text())
    assert "Kafka" in saved["skills"]["Big Data & Data Engineering"]      # appended, not replaced
    assert "Spark" in saved["skills"]["Big Data & Data Engineering"]
    # /undo restores the prior list
    agent.undo_last(st, profile_path=temp_profile)
    assert "Kafka" not in json.loads(temp_profile.read_text())["skills"]["Big Data & Data Engineering"]


def test_add_project_then_bullet_by_title(temp_profile):
    """A new project is appended to the (list) projects, then a bullet addressed by TITLE lands in
    that project's bullets - the exact path that used to 500 (list indexed by a string)."""
    st = store.new_run("enhance")
    st.pending = [Proposal(kind="add_project", path=["projects"],
                           value={"title": "ATS Resumaker 2.0", "date": "Jan 2026 - Aug 2026"},
                           source_quote="ATS Resumaker 2.0", preview="add project").__dict__]
    assert agent.apply_pending(st, profile_path=temp_profile) == 1
    saved = json.loads(temp_profile.read_text())
    assert [p["title"] for p in saved["projects"]] == ["ATS Resumaker 2.0"]

    # add a bullet addressing the project by title (model drops the "2.0" suffix here on purpose)
    st.pending = [Proposal(kind="add_bullet", path=["projects", "ATS Resumaker"],
                           value="Cut median scrape latency from 8s to under 400ms",
                           source_quote="under 400ms", preview="add latency bullet").__dict__]
    assert agent.apply_pending(st, profile_path=temp_profile) == 1
    saved = json.loads(temp_profile.read_text())
    bullets = [b["text"] for b in saved["projects"][0]["bullets"]]
    assert "Cut median scrape latency from 8s to under 400ms" in bullets

    # /undo removes just that bullet
    agent.undo_last(st, profile_path=temp_profile)
    after = json.loads(temp_profile.read_text())["projects"][0]["bullets"]
    assert all("400ms" not in b["text"] for b in after)


def test_add_project_is_idempotent(temp_profile):
    """The model re-proposes the same project every turn; re-adding must not duplicate it. A re-add
    with no bullets is a no-op (uncounted); a re-add carrying bullets folds them into the existing
    project."""
    st = store.new_run("enhance")
    def mk(val: dict) -> dict:
        return Proposal(kind="add_project", path=["projects"], value=val,
                        source_quote="ATS Resumaker", preview="add project").__dict__
    st.pending = [mk({"title": "ATS Resumaker 2.0", "bullets": ["first bullet"]})]
    assert agent.apply_pending(st, profile_path=temp_profile) == 1

    # bare re-add of the same title -> no-op, not counted, no duplicate
    st.pending = [mk({"title": "ATS Resumaker 2.0"})]
    assert agent.apply_pending(st, profile_path=temp_profile) == 0
    saved = json.loads(temp_profile.read_text())
    assert [p["title"] for p in saved["projects"]].count("ATS Resumaker 2.0") == 1

    # re-add carrying a new bullet -> folded into the existing project (still one project)
    st.pending = [mk({"title": "ATS Resumaker 2.0", "bullets": ["second bullet"]})]
    assert agent.apply_pending(st, profile_path=temp_profile) == 1
    saved = json.loads(temp_profile.read_text())
    proj = [p for p in saved["projects"] if p["title"] == "ATS Resumaker 2.0"]
    assert len(proj) == 1
    assert [b["text"] for b in proj[0]["bullets"]] == ["first bullet", "second bullet"]


def test_apply_pending_skips_unresolvable_bullet(temp_profile):
    """A bullet for a project that doesn't exist must be skipped (recorded), not 500 the whole turn."""
    st = store.new_run("enhance")
    st.pending = [Proposal(kind="add_bullet", path=["projects", "Nonexistent Project"],
                           value="some bullet", source_quote="some bullet",
                           preview="orphan bullet").__dict__]
    n = agent.apply_pending(st, profile_path=temp_profile)   # must not raise
    assert n == 0
    assert st.meta.get("apply_errors") == ["orphan bullet"]


# ---- intake thin-spot detector (deterministic) ---------------------------
def test_detect_thin_spots():
    prof = {"summary": "", "skills": {"a": ["x"]},
            "experience": [
                {"title": "MLE", "organization": "Granite",
                 "bullets": [{"text": "Reduced query time drastically", "metrics": []}]},
                {"title": "SWE", "organization": "Bajaj", "bullets": []},
            ]}
    spots = " ".join(intake.detect_thin_spots(prof)).lower()
    assert "summary" in spots            # empty summary flagged
    assert "no bullet" in spots          # empty-bullets role flagged
    assert "measurably" in spots or "metric" in spots  # outcome-without-metric flagged


# ---- full enhance turn with a fake LLM (turn loop end-to-end) -------------
class _FakeLLM:
    def __init__(self, payload): self._p = payload
    def complete_json(self, prompt, **kw): return self._p


def test_enhance_turn_proposes_then_confirms(temp_profile, monkeypatch):
    from resumaker.persistence import profile as ps
    monkeypatch.setattr(ps, "profile_text", lambda: "current profile")
    fake = _FakeLLM({
        "proposals": [{"kind": "add_skill", "path": ["skills", "Big Data & Data Engineering"],
                       "value": "Kafka", "source_quote": "I used Kafka", "preview": "add Kafka"}],
        "reply": "I'll add Kafka. Reply yes to apply.", "question": ""})
    st = enhance.start()
    reply = enhance.say(st, "I used Kafka on the fraud stream", llm=fake, profile_path=temp_profile)
    assert st.pending and st.pending[0]["value"] == "Kafka"
    assert "kafka" in reply.lower()
    # confirm -> applied
    reply2 = enhance.say(st, "yes", llm=fake, profile_path=temp_profile)
    assert "applied 1" in reply2.lower()
    assert "Kafka" in json.loads(temp_profile.read_text())["skills"]["Big Data & Data Engineering"]


def test_yes_with_trailing_info_applies_then_analyzes(temp_profile, monkeypatch):
    """'yes, <new info>' must APPLY the pending change AND analyze the tacked-on info in one turn -
    the footgun where the confirmation used to be dropped and the info misattributed."""
    from resumaker.persistence import profile as ps
    monkeypatch.setattr(ps, "profile_text", lambda: "current profile")
    # the remainder turn's LLM response proposes a date bullet
    fake = _FakeLLM({"proposals": [{"kind": "add_bullet", "path": ["projects", "ATS Resumaker 2.0"],
                                    "value": "Built Jan-Aug 2026", "source_quote": "Jan to Aug 2026",
                                    "preview": "add date bullet"}],
                     "reply": "Noted the timeframe.", "question": ""})
    st = store.new_run("enhance")
    # seed a pending project confirmation
    st.pending = [Proposal(kind="add_project", path=["projects"],
                           value={"title": "ATS Resumaker 2.0", "bullets": ["core bullet"]},
                           source_quote="ATS Resumaker", preview="add project").__dict__]
    reply = agent.run_turn(st, "yes, I built it from Jan to Aug 2026",
                           build_prompt=enhance._build_prompt, llm=fake, profile_path=temp_profile)
    assert "applied 1" in reply.lower()          # the project was applied
    assert "noted the timeframe" in reply.lower()  # AND the trailing info was analyzed
    assert st.pending and st.pending[0]["value"] == "Built Jan-Aug 2026"  # date bullet now pending
    saved = json.loads(temp_profile.read_text())
    assert any(p["title"] == "ATS Resumaker 2.0" for p in saved["projects"])


def test_yes_but_redirect_does_not_apply(temp_profile, monkeypatch):
    """'yes but ...' is a redirect - it must NOT auto-apply; it runs an analysis turn instead."""
    from resumaker.persistence import profile as ps
    monkeypatch.setattr(ps, "profile_text", lambda: "current profile")
    fake = _FakeLLM({"proposals": [], "reply": "Got it, not that one.", "question": ""})
    st = store.new_run("enhance")
    st.pending = [{"kind": "add_skill", "path": ["skills", "x"], "value": "Y",
                   "source_quote": "q", "preview": "p"}]
    reply = agent.run_turn(st, "yes but actually put it under CurateAI",
                           build_prompt=enhance._build_prompt, llm=fake, profile_path=temp_profile)
    assert st.applied == []                       # nothing was applied
    assert "got it" in reply.lower()


def test_stop_is_deterministic_and_discards_pending(temp_profile):
    st = store.new_run("enhance")
    st.pending = [{"kind": "add_skill", "path": ["skills", "x"], "value": "Y",
                   "source_quote": "q", "preview": "p"}]
    reply = agent.run_turn(st, "/stop", build_prompt=lambda s, m: ("", ""), llm=_FakeLLM({}))
    assert st.state == "stopped" and st.pending == []
    assert "stopped" in reply.lower()
