"""Profile chat-agent API (POC wiring for local testing).

Thin HTTP surface over `pocs/profile_agent` so the web app can drive the three flows:

  POST /v1/profile-agent            start a run {mode: enhance|gapchat|intake, report_run_id?, resume_text?}
  GET  /v1/profile-agent/{id}       poll state (events, history, pending proposals, meta)
  POST /v1/profile-agent/{id}/say   send a message or slash command
  POST /v1/profile-agent/{id}/stop  hard stop

`pocs` is imported lazily inside handlers so app startup never depends on it (the deployed image may
not ship `pocs/`). Conversational turns run inline (one fast LLM call); a gapchat `/generate` runs in
a background thread because it triggers the full re-match + resume pipeline (minutes) - the client
polls GET for the score delta.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from apps.api.security import require_token

router = APIRouter(prefix="/v1/profile-agent", tags=["profile-agent"],
                   dependencies=[Depends(require_token)])

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="profile-agent")


class StartIn(BaseModel):
    mode: str                       # enhance | gapchat | intake
    report_run_id: str | None = None
    resume_text: str | None = None


class SayIn(BaseModel):
    message: str


def _state(run_id: str) -> dict:
    from pocs.profile_agent import store
    return asdict(store.load(run_id))


@router.post("", status_code=201)
def start(body: StartIn) -> dict:
    from pocs.profile_agent import enhance, gapchat, intake
    mode = body.mode.strip().lower()
    if mode == "enhance":
        return asdict(enhance.start())
    if mode == "gapchat":
        if not body.report_run_id:
            raise HTTPException(400, "gapchat needs report_run_id")
        try:
            return asdict(gapchat.start(body.report_run_id))
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from None
    if mode == "intake":
        if not (body.resume_text or "").strip():
            raise HTTPException(400, "intake needs resume_text")
        try:
            return asdict(intake.run_intake_text(body.resume_text))
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        except Exception as e:  # noqa: BLE001 - surface a parse failure, don't 500
            raise HTTPException(502, f"resume parse failed: {e}") from None
    raise HTTPException(400, f"unknown mode {body.mode!r}")


@router.post("/parse")
async def parse(request: Request) -> dict:
    """Parse a resume into a profile-shaped doc WITHOUT persisting (the client reviews it, then POSTs
    it to /v1/profile/seed to apply). Accepts either an uploaded file as the raw request body (with a
    `?filename=` query param) or a JSON body {"text": "..."} - so no python-multipart dependency is
    needed, and the filename survives the BFF proxy (which forwards the query string, not headers)."""
    from pocs.profile_agent import intake
    filename = request.query_params.get("filename", "")
    try:
        if filename:
            raw = await request.body()
            if not raw:
                raise HTTPException(422, "empty file upload")
            text = intake.extract_upload(raw, filename)
        else:
            data = await request.json()
            text = str((data or {}).get("text") or "")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except Exception as e:  # noqa: BLE001 - bad body / unreadable file
        raise HTTPException(422, f"couldn't read the input: {e}") from None

    try:
        parsed, thin = intake.parse_resume(text)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except Exception as e:  # noqa: BLE001 - LLM/parse failure
        raise HTTPException(502, f"resume parse failed: {e}") from None
    n_skills = sum(len(v) for v in (parsed.get("skills") or {}).values() if isinstance(v, list))
    return {"profile": parsed, "thin_spots": thin,
            "summary": {"experience": len(parsed.get("experience") or []),
                        "projects": len(parsed.get("projects") or []), "skills": n_skills}}


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    from pocs.profile_agent import store
    if not store.exists(run_id):
        raise HTTPException(404, "run not found")
    return _state(run_id)


@router.post("/{run_id}/say")
def say(run_id: str, body: SayIn) -> dict:
    from pocs.profile_agent import enhance, gapchat, store
    if not store.exists(run_id):
        raise HTTPException(404, "run not found")
    st = store.load(run_id)
    if st.state in ("stopped", "done", "error"):
        raise HTTPException(409, f"run is {st.state}")
    fn = {"enhance": enhance.say, "gapchat": gapchat.say}.get(st.mode)
    if fn is None:
        raise HTTPException(400, f"mode {st.mode!r} is not conversational")

    # /generate kicks off the full re-match + resume pipeline - run it off-request and let the
    # client poll. Everything else is a single fast LLM turn, safe to run inline.
    if st.mode == "gapchat" and body.message.strip().lower().startswith("/generate"):
        st.add_event("generate", "queued", "re-match + resume generation started")
        st.state = "running"
        store.save(st)

        def _run() -> None:
            s = store.load(run_id)
            gapchat.say(s, "/generate")

        _pool.submit(_run)
        return _state(run_id)

    fn(st, body.message)
    return _state(run_id)


@router.post("/{run_id}/stop")
def stop(run_id: str) -> dict:
    from pocs.profile_agent import store
    if not store.exists(run_id):
        raise HTTPException(404, "run not found")
    st = store.load(run_id)
    st.state = "stopped"
    st.pending = []
    st.add_event("stop", "ok", "stopped by user")
    store.save(st)
    return _state(run_id)
