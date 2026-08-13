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
    # When generating from a tracked job, the frontend passes that job's stable run_id (the match
    # slug) so the tailored resume lands in the SAME run folder as its match report - it overwrites
    # report.json with the full (resume-bearing) version, so the report page shows the documents on
    # reload with no separate id to remember. Omitted for ad-hoc runs -> a fresh id is minted.
    run_id: str | None = None
    gate: bool = False
    make_cover_letter: bool = True
    target_pages: int = 1
    semantic_method: str = "lexical"


class RunStarted(BaseModel):
    run_id: str
    status: str = "running"


@router.post("", response_model=RunStarted, status_code=202)
def start_run(req: RunRequest) -> RunStarted:
    """Start a pipeline run. Mints the id here so it's stable across the DB, artifacts, and any
    queue payload, then hands off to the config-selected queue (in-process locally, Cloud Tasks
    in the cloud - same call site)."""
    import uuid

    from apps.api.jobs.queue import get_job_queue

    run_id = req.run_id or uuid.uuid4().hex[:12]
    # Flip the run to 'running' up front. A generation reuses the tracked job's run_id, whose row
    # still says 'matched' - without this reset the progress poll sees that terminal status and
    # reports done on the first tick, snapping the UI back to 'Generate' before the run starts.
    db.set_run_status(run_id, "running", req.url)
    get_job_queue().submit_pipeline(run_id, req.url, {
        "gate": req.gate, "make_cover_letter": req.make_cover_letter,
        "target_pages": req.target_pages, "semantic_method": req.semantic_method,
    })
    return RunStarted(run_id=run_id)


class ResumeUpload(BaseModel):
    # The PDF as base64 (bare or a `data:application/pdf;base64,...` URL - both accepted). Base64
    # over the existing JSON proxy avoids a multipart dependency and mirrors the extension's
    # base64-screenshot capture. `filename` is cosmetic (shown on the report).
    pdf_base64: str
    filename: str = "resume.pdf"


@router.post("/{run_id}/resume-upload", status_code=200)
def upload_resume(run_id: str, body: ResumeUpload) -> dict:
    """Attach an owner-supplied resume PDF to a run instead of generating one. Stores it in the
    run's artifact store as resume.pdf (durable in GCS after publish) and flags report.json so the
    report page shows it; DOCX + cover letter stay 'unavailable' since only a PDF was supplied.
    Bounded to 15MB and must be a real PDF (%PDF header). No DB migration needed - report.json is
    the source of truth for what documents a run has, and it already rides GCS."""
    import base64

    raw = body.pdf_base64.strip()
    if raw.startswith("data:"):                      # tolerate a data: URL straight from the browser
        raw = raw.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception:  # noqa: BLE001 - malformed base64 -> 400, never a 500
        raise HTTPException(400, "invalid base64 PDF") from None
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "PDF too large (max 15MB)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "not a PDF (missing %PDF header)")

    from resumaker.persistence.artifacts import get_artifact_store
    store = get_artifact_store()
    # The uploaded PDF is the single source of truth for this run's resume, so clear any prior
    # resume artifacts first (a previously *generated* .pdf/.docx) - otherwise find(".pdf") could
    # resolve the stale one, and a leftover .docx would look downloadable when it no longer matches.
    store.purge(run_id, (".pdf", ".docx"))
    run_dir = store.local_run_dir(run_id)
    (run_dir / "resume.pdf").write_bytes(data)

    # Flag report.json so the report page renders the resume tab. Prefer the local copy; on a
    # scale-to-zero instance the run dir is empty, so pull report.json from the store (GCS) instead.
    rep = None
    local_report = run_dir / "report.json"
    if local_report.is_file():
        rep = json.loads(local_report.read_text())
    else:
        raw_rep = store.open(run_id, "report.json")
        if raw_rep:
            rep = json.loads(raw_rep)
    if rep is not None:
        rep["resume"] = {"uploaded": True, "filename": body.filename or "resume.pdf"}
        rep["ats"] = None                            # an uploaded resume has no ATS score
        local_report.write_text(json.dumps(rep))
    store.publish(run_id)
    return {"ok": True, "uploaded": True}


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
# `screenshot.png`/`screenshot.jpg` is the browser-extension capture (full-page shot, PNG or JPEG
# for tall pages; served as a thumbnail on the report page; GCS redirects to a signed URL).
_ARTIFACTS = {"report.json", "cover_letter.txt", "content.json", "JD.txt",
              "resume_extracted_text.txt", "status.json", "screenshot.png", "screenshot.jpg"}


# Content types for a direct (attachment) download, so the browser saves the real file instead of
# following a signed-URL redirect. Keyed by suffix.
_DL_MEDIA = {".pdf": "application/pdf", ".docx":
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@router.get("/{run_id}/artifacts/{name}")
def get_artifact(run_id: str, name: str, download: bool = False):
    """Serve an artifact via the config-selected store. Default: local disk streams inline; GCS
    redirects to a short-lived signed URL (used for the inline PDF preview). With `?download=1` the
    bytes are streamed THROUGH the API with a Content-Disposition attachment header (works on both
    backends, no redirect) so the PDF/DOCX save directly. Role-slug filenames (resume.pdf/docx)
    resolve by suffix within the run dir."""
    from fastapi.responses import FileResponse, RedirectResponse, Response

    from resumaker.persistence.artifacts import get_artifact_store
    store = get_artifact_store()
    run_dir = store.local_run_dir(run_id)
    resolved = name
    if name in ("resume.pdf", "resume.docx"):  # role-slug filename; resolve by suffix
        suffix = "." + name.split(".")[1]
        # Resolve from the store (bucket in cloud), not the local dir - on a scale-to-zero instance
        # the local run dir is empty (artifacts live in GCS after publish), which 404'd resume.pdf/docx.
        resolved_name = store.find(run_id, suffix)
        if resolved_name is None:
            raise HTTPException(404, f"no {suffix} artifact")
        resolved = resolved_name
    elif name not in _ARTIFACTS:
        raise HTTPException(400, "unknown artifact")

    if download:
        # Stream the bytes with an attachment disposition so it downloads directly (no signed-URL
        # hop). store.open() reads from the bucket in cloud / local disk otherwise.
        data = store.open(run_id, resolved)
        if data is None:
            raise HTTPException(404, "artifact not found")
        suffix = Path(resolved).suffix.lower()
        media = _DL_MEDIA.get(suffix, "application/octet-stream")
        return Response(content=data, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    signed = store.url(run_id, resolved)         # non-None only for the GCS backend
    if signed:
        return RedirectResponse(signed)
    path = run_dir / Path(resolved).name         # basename only - no path traversal
    if not path.is_file():
        raise HTTPException(404, "artifact not found")
    return FileResponse(path)
