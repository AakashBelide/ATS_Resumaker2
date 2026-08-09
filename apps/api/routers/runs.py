"""Pipeline runs: start, poll, list, stream progress (SSE), and download artifacts.

A POST starts a background run and returns its id immediately (the pipeline is minutes
long). Clients then either poll GET /{id} or subscribe to the SSE event stream, and
finally fetch artifacts (resume PDF/DOCX, cover letter, report).
"""
from __future__ import annotations

import asyncio
import queue
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

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


@router.get("/{run_id}/events")
async def stream_events(run_id: str) -> EventSourceResponse:
    """Server-Sent Events: one message per stage transition until the run ends. Reuses
    the same progress stream the CLI/`watch` render."""
    h = manager.handle(run_id)
    if h is None:
        raise HTTPException(404, "run not found or already reaped")

    async def gen():
        while True:
            try:
                ev = h.events.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.25)
                continue
            if ev.get("stage") == "__end__":
                yield {"event": "end", "data": "done"}
                break
            yield {"event": "progress", "data": f'{ev["stage"]}:{ev["status"]}:{ev["detail"]}'}

    return EventSourceResponse(gen())


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
