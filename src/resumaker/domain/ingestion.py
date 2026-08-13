"""Domain models for the job-watchlist / ingestion subsystem (RI.1-RI.4).

These mirror the derived SQLite tables (`companies`, `jobs`, `runs`). The board-
listing adapters (`providers/sources/`) emit `JobPosting`-like postings that get
normalized into `JobRecord`s, deduped, and (optionally) fed to the pipeline, which
records a `RunRecord`. Defined now so the schema and seams exist from day one, even
though the crawler/scheduler land after the API/CLI core.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["new", "seen", "queued", "processed", "applied", "skipped"]
RunStatus = Literal["pending", "running", "done", "error", "gated_out", "matched"]
# Application lifecycle for a tracked job (RA.2). `interested` = added, match run done.
TrackerStage = Literal["interested", "applied", "interview", "offer", "rejected", "skipped"]
TRACKER_STAGES: tuple[str, ...] = (
    "interested", "applied", "interview", "offer", "rejected", "skipped")

# Agentic onboarding run lifecycle (Phase C). deterministic-first -> agent fallback;
# `needs_input` pauses for a human answer; `killed`=time/budget guard, `stopped`=manual.
OnboardState = Literal[
    "running", "needs_input", "resolved", "drafted", "unresolved", "killed", "stopped", "error"]


class BoardRef(BaseModel):
    """A company's posting board on one source (e.g. Greenhouse token 'databricks')."""
    source: str                        # greenhouse | lever | ashby | workday
    token: str                         # board slug / company id used by that source's API
    extra: dict[str, str] = Field(default_factory=dict)  # e.g. workday host/tenant


class Company(BaseModel):
    """A watched company. `boards` lists where to poll for its openings."""
    id: int | None = None
    name: str
    active: bool = True
    boards: list[BoardRef] = Field(default_factory=list)
    created_at: datetime | None = None


class JobRecord(BaseModel):
    """A single ingested posting. Dedup identity is `(source, external_id)`;
    `content_hash` (normalized JD text) detects edits/re-posts so we only re-run on
    real change."""
    id: int | None = None
    source: str
    external_id: str                   # the source's stable posting id
    url: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    content_hash: str = ""
    status: JobStatus = "new"
    comp: str = ""                     # pay summary, only when the ATS states it (else empty)
    posted_at: str = ""                # source's publish/updated date when available
    first_seen: datetime | None = None  # when WE first saw it (reliable freshness proxy)
    last_seen: datetime | None = None

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.external_id}"


class RunRecord(BaseModel):
    """A pipeline execution (history/analytics). Files under `out_dir` stay canonical;
    this row is the queryable index over them."""
    id: str                            # run id (also the out-dir slug)
    job_id: int | None = None          # FK to jobs when triggered by ingestion
    url: str = ""
    out_dir: str = ""
    status: RunStatus = "pending"
    recommend_apply: bool | None = None
    fit_0_100: float | None = None
    ats_overall: float | None = None
    fact_gate_pass: bool | None = None
    ats_verify_pass: bool | None = None
    page_count: int | None = None
    cost_usd: float = 0.0
    error: str = ""
    created_at: datetime | None = None
    finished_at: datetime | None = None


class OnboardEvent(BaseModel):
    """One progress event in an onboarding run's timeline (frontend renders these)."""
    stage: str                         # start | deterministic | agent | resume | stop
    status: str                        # start | done | skip | error | needs_input
    detail: str = ""
    ts: float = 0.0


class OnboardingRun(BaseModel):
    """An agentic onboarding attempt (Phase C). The DB row is the source of truth so the run
    survives restarts and the frontend can poll it (+ pop a dialog when `state==needs_input`)."""
    id: str                            # run id
    name: str
    careers_url: str = ""
    method: str = ""                   # deterministic | agent
    state: OnboardState = "running"
    question: str = ""                 # set when state == needs_input
    board: BoardRef | None = None      # the resolved board (state == resolved)
    evidence: dict = Field(default_factory=dict)   # e.g. {count, board_name, sample}
    events: list[OnboardEvent] = Field(default_factory=list)
    cost_usd: float = 0.0
    turns: int = 0
    error: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TrackerEntry(BaseModel):
    """A job the owner is actively pursuing (RA.2). Added from Discovery / the extension;
    on add we run the match pipeline (fit/gap/sponsorship/keywords, NO resume/cover) and
    store the outcome + an application-lifecycle `stage`. Resume/cover are triggered later
    by hand. Files under the match run's `out_dir` stay canonical; this row indexes them."""
    id: int | None = None
    job_id: int | None = None          # FK to jobs when added from the watchlist
    url: str = ""
    company: str = ""
    title: str = ""
    stage: TrackerStage = "interested"
    run_id: str = ""                   # the match RunRecord.id (fit/gap/sponsorship/keywords)
    fit_0_100: float | None = None
    recommend_apply: bool | None = None
    sponsorship: str = ""              # resolved verdict, e.g. "likely" / "not_eligible"
    match_error: str | None = None     # set when the match failed; lets the UI show "failed"
                                       # (not an eternal "matching…") and offer a retry
    location: str = ""                 # posting location (from the watchlist or structured JD)
    salary: str = ""                   # stated pay range when the posting/JD discloses it
    notes: str = ""
    # Raw JD text captured by the browser extension (the page's visible text). When present the
    # match SKIPS the server-side scrape and structures THIS text instead (the extension already
    # had the page loaded). Kept server-side only: `exclude=True` drops it from every API response
    # so the (up to ~200 KB) blob never rides along on the tracker list / add / capture payloads.
    captured_jd: str = Field(default="", exclude=True)
    created_at: datetime | None = None
    updated_at: datetime | None = None
