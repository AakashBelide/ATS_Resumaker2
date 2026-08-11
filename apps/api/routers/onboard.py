"""Agentic onboarding API (Phase C): async company -> ATS board resolution, human-in-the-loop.

  POST /v1/onboard             start an async run  -> 202 {id, state, ...}
  GET  /v1/onboard             list recent runs
  GET  /v1/onboard/{id}        poll a run (state, events, question, board)
  POST /v1/onboard/{id}/input  answer a `needs_input` pause (resume)
  POST /v1/onboard/{id}/stop   manual kill (Stop button)

Deterministic-first ($0) runs inline in the background task; the sandboxed agent fallback is opt-in
(RESUMAKER_ONBOARD_AGENT_ENABLED). On `resolved`, the company is added to the watchlist.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.security import require_token
from resumaker import onboarding
from resumaker.domain import OnboardingRun

router = APIRouter(prefix="/v1/onboard", tags=["onboarding"],
                   dependencies=[Depends(require_token)])


class OnboardStart(BaseModel):
    name: str
    careers_url: str | None = None


class InputIn(BaseModel):
    answer: str


@router.post("", response_model=OnboardingRun, status_code=202)
def start(body: OnboardStart) -> OnboardingRun:
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    return onboarding.start(body.name, body.careers_url)


@router.get("", response_model=list[OnboardingRun])
def list_runs(limit: int = 50) -> list[OnboardingRun]:
    return onboarding.list_runs(limit=limit)


@router.get("/{run_id}", response_model=OnboardingRun)
def get_run(run_id: str) -> OnboardingRun:
    run = onboarding.get(run_id)
    if run is None:
        raise HTTPException(404, "onboarding run not found")
    return run


@router.post("/{run_id}/input", response_model=OnboardingRun)
def provide_input(run_id: str, body: InputIn) -> OnboardingRun:
    try:
        return onboarding.provide_input(run_id, body.answer)
    except KeyError:
        raise HTTPException(404, "onboarding run not found") from None


@router.post("/{run_id}/stop", response_model=OnboardingRun)
def stop(run_id: str) -> OnboardingRun:
    run = onboarding.stop(run_id)
    if run is None:
        raise HTTPException(404, "onboarding run not found")
    return run
