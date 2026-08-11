"""Pipeline runs: start, poll status + progress, list, and download artifacts.

A POST starts a background run and returns its id immediately (the pipeline is minutes
long). Clients poll GET /{id} for the terminal status and GET /{id}/progress for the live
stage, then fetch artifacts (resume PDF/DOCX, cover letter, report).

Progress is exposed by POLLING (not SSE): a scale-to-zero / multi-instance serverless
deployment can't hold an open stream, and the in-process event queue isn't visible to
another instance. `progress` reads the run's `status.json` snapshot (written by the
ProgressReporter to the run dir - shared storage in the cloud), so any instance can serve
it. Same file the CLI `watch` renders; nothing here is stateful.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.jobs.worker import manager
from apps.api.security import require_token
from resumaker.config import get_settings
from resumaker.domain import RunRecord
from resumaker.persistence import db

router = APIRouter(prefix="/v1/runs", tags=["runs"], dependencies=[Depends(require_token)])


class RunRequest(BaseModel):
    url: str
    gate: bool = False
    make_cover_letter: bool = True
    target_pages: int = 1
    semantic_method: str = "lexical"


class RunStarted(BaseModel):
    run_id: str
    status: str = "running"


@router.post("", response_model=RunStarted, status_code=202)
def start_run(req: RunRequest) -> RunStarted:
    run_id = manager.start(req.url, gate=req.gate, make_cover_letter=req.make_cover_letter,
                           target_pages=req.target_pages, semantic_method=req.semantic_method)
    return RunStarted(run_id=run_id)


@router.get("", response_model=list[RunRecord])
def list_runs(limit: int = 50) -> list[RunRecord]:
    return db.list_runs(limit=limit)


@router.get("/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    rec = db.get_run(run_id)
    if rec is None:
        # still-running (or unknown) - synthesize a pending record from the live handle
        h = manager.handle(run_id)
        if h is None:
            raise HTTPException(404, "run not found")
        return RunRecord(id=run_id, url=h.url,
                         status="done" if h.finished else "running")
    return rec


class RunProgress(BaseModel):
    current: str = ""            # the stage in flight (e.g. "tailor", "ats_verify")
    done: bool = False           # the run has ended (success OR error - poll GET /{id} for which)
    elapsed: float = 0.0
    stages: list[dict] = []      # per-stage [{stage,status,detail,elapsed}] in order


@router.get("/{run_id}/progress", response_model=RunProgress)
def get_progress(run_id: str) -> RunProgress:
    """Current progress snapshot for a run, read from its `status.json` (poll this instead of
    a stream). Before the run dir/status exists yet, returns an empty in-progress snapshot so
    the client can keep polling. When the run's DB row is terminal, reports done even if the
    file is missing (e.g. reaped)."""
    status_path = get_settings().output_root / run_id / "status.json"
    if status_path.is_file():
        try:
            snap = json.loads(status_path.read_text())
            return RunProgress(current=snap.get("current", ""), done=bool(snap.get("done")),
                               elapsed=float(snap.get("elapsed", 0.0)), stages=snap.get("stages", []))
        except (json.JSONDecodeError, OSError):
            pass  # mid-write or unreadable - fall through to a keep-polling snapshot
    rec = db.get_run(run_id)
    if rec is not None and rec.status in ("done", "error", "matched"):
        return RunProgress(current=rec.status, done=True)
    return RunProgress()  # unknown/just-started - empty snapshot, client keeps polling


# Only these artifact names are servable, mapped by suffix within the run dir.
_ARTIFACTS = {"report.json", "cover_letter.txt", "content.json", "JD.txt",
              "resume_extracted_text.txt", "status.json"}


@router.get("/{run_id}/artifacts/{name}")
def get_artifact(run_id: str, name: str):
    from fastapi.responses import FileResponse
    run_dir = get_settings().output_root / run_id
    if not run_dir.is_dir():
        raise HTTPException(404, "run dir not found")
    if name in ("resume.pdf", "resume.docx"):  # role-slug filename; resolve by suffix
        suffix = "." + name.split(".")[1]
        match = next((f for f in run_dir.glob(f"*{suffix}")), None)
        if match is None:
            raise HTTPException(404, f"no {suffix} artifact")
        return FileResponse(match)
    if name not in _ARTIFACTS:
        raise HTTPException(400, "unknown artifact")
    path = run_dir / Path(name).name  # basename only - no path traversal
    if not path.is_file():
        raise HTTPException(404, "artifact not found")
    return FileResponse(path)
