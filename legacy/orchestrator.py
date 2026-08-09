"""Phase-2 orchestrator: chain every stage into one call (blueprint 16/19).

Deterministic mechanics stay in code; cognitive stages are the POC modules. After
structuring the JD, the three independent analyses (keywords, gap, sponsorship) run
as a PARALLEL fan-out (the pragmatic equivalent of sub-agents; a Claude Agent SDK
fan-out can slot in behind the same interface later). A progress callback streams
stage status (ready for SSE in Phase 4/5).

    from orchestrator import run_pipeline
    result = run_pipeline("https://boards.greenhouse.io/.../jobs/123")
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from core import profile as prof
from core.progress import ProgressReporter
from core.schemas import PipelineResult
from pocs.apply_decision import decide_apply
from pocs.ats import score_ats
from pocs.ats_verify import verify_ats
from pocs.cover_letter import write_cover_letter
from pocs.fact_gate import verify_resume
from pocs.gap import analyze_gaps
from pocs.jd_structure import structure_jd
from pocs.keywords import extract_keywords
from pocs.resume import generate_resume
from pocs.resume.render_pdf import extract_text
from pocs.role_fit import score_fit
from pocs.scrape_jd import scrape
from pocs.sponsorship import sponsor_signal
from pocs.sponsorship.resolve import resolve_sponsorship

Progress = Callable[[str, str, str], None]
_OUT = Path(__file__).resolve().parent.parent / "outputs"


def _noop(stage: str, status: str, detail: str = "") -> None:
    pass


def _slug(*parts: str) -> str:
    import re
    s = "-".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")[:60] or "job"


def run_pipeline(url: str | None = None, *, job=None, out_dir: str | None = None,
                 target_pages: int = 1, gate: bool = False, parallel: bool = True,
                 make_cover_letter: bool = True, semantic_method: str = "lexical",
                 on_progress: Progress | None = None) -> PipelineResult:
    """Run the full pipeline for one JD.

    url            : JD URL to scrape (skip if `job` is supplied).
    job            : a pre-structured JobPosting (skips scrape+structure; for tests).
    gate           : if True, stop before resume/cover when apply-decision is negative.
    parallel       : fan out keywords/gap/sponsorship concurrently.
    on_progress    : callback(stage, status, detail); status in start|done|skip|error.
    """
    p = on_progress or _noop
    t = {}
    res = PipelineResult(url=url or "")

    # Progress sink: forwards to the CLI callback AND persists status.json/progress.jsonl.
    reporter = ProgressReporter(
        url=url or "",
        on_event=lambda ev: p(ev.stage, ev.status,
                              ev.detail or (f"{ev.elapsed}s" if ev.elapsed else "")),
        out_dir=out_dir)

    def timed(stage, fn):
        reporter.emit(stage, "start")
        t0 = time.time()
        try:
            out = fn()
        except Exception as e:  # noqa: BLE001
            reporter.emit(stage, "error", str(e))
            raise
        t[stage] = round(time.time() - t0, 2)
        reporter.emit(stage, "done")
        return out

    try:
        # 1) scrape + structure (unless a job was passed in)
        if job is None:
            raw = timed("scrape", lambda: scrape(url))
            job = timed("structure", lambda: structure_jd(raw, model="sonnet"))
        res.job = job

        # resolve the out-dir now so status.json + all artifacts land together
        resolved_out = out_dir or str(_OUT / _slug(job.company, job.title))
        out_dir = resolved_out
        if reporter.out_dir is None:
            reporter.set_out_dir(resolved_out)

        # 2) parallel fan-out: keywords | gap | sponsorship (independent)
        def _kw():
            return extract_keywords(job)

        def _gap():
            return analyze_gaps(job)

        def _spon():
            return sponsor_signal(job.company) if job.company else None

        if parallel:
            reporter.emit("analyze", "start", "keywords|gap|sponsorship (parallel)")
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=3) as ex:
                f_kw, f_gap, f_spon = ex.submit(_kw), ex.submit(_gap), ex.submit(_spon)
                ks, gap, sig = f_kw.result(), f_gap.result(), f_spon.result()
            t["analyze"] = round(time.time() - t0, 2)
            reporter.emit("analyze", "done")
        else:
            ks = timed("keywords", _kw)
            gap = timed("gap", _gap)
            sig = timed("sponsorship", _spon)
        res.keyword_set, res.gap = ks, gap

        # 3) fit -> sponsorship verdict -> apply decision
        res.fit = timed("fit", lambda: score_fit(job, gap=gap))
        verdict = timed("sponsorship_resolve", lambda: resolve_sponsorship(job, sig))
        res.sponsorship = dict(verdict.__dict__)
        res.decision = timed("apply", lambda: decide_apply(job, res.fit, verdict))

        # 4) apply gate (optional): don't spend generation compute on a hard no
        if gate and not res.decision.recommend_apply:
            res.gated_out = True
            reporter.emit("gate", "skip", "apply-decision negative; skipping resume/cover")
            res.timings = t
            _save(res, url, job)
            reporter.finish()
            return res

        # 5) resume: tailor -> deterministic skills -> docx/pdf -> fact-gate/verify/score
        doc = timed("resume", lambda: generate_resume(job, keyword_set=ks, gap=gap,
                                                       target_pages=target_pages,
                                                       out_dir=out_dir))
        res.resume = doc
        res.fact_gate = timed("fact_gate", lambda: verify_resume(doc.content))
        res.ats_verify = timed("ats_verify",
                               lambda: verify_ats(job, doc.content, pdf_path=doc.pdf_path))
        res.ats = timed("ats_score", lambda: score_ats(job, doc.content, keyword_set=ks,
                                                        semantic_method=semantic_method))

        # 6) cover letter (BEST-EFFORT: a late optional stage must never discard the
        #    already-generated resume; a failure is a warning, not a fatal error).
        if make_cover_letter:
            try:
                res.cover_letter = timed("cover_letter", lambda: write_cover_letter(job, gap=gap))
            except Exception as e:  # noqa: BLE001
                res.warnings.append(f"cover_letter failed (resume is unaffected): {e}")

        res.timings = t
        _save(res, url, job)
        reporter.finish()
        return res
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"
        res.timings = t
        reporter.emit("pipeline", "error", res.error)
        reporter.finish()
        return res


def _save(res: PipelineResult, url: str | None, job) -> None:
    """Write human-readable artifacts + a machine report.json next to the resume."""
    if res.resume and res.resume.pdf_path:
        out = Path(res.resume.pdf_path).parent
    else:
        out = _OUT / _slug(job.company, job.title)
    out.mkdir(parents=True, exist_ok=True)
    res.out_dir = str(out)

    (out / "JD.txt").write_text(f"{url or ''}\n\n{job.raw_text}")
    if res.resume:
        (out / "content.json").write_text(res.resume.content.model_dump_json(indent=1))
        try:
            (out / "resume_extracted_text.txt").write_text(extract_text(res.resume.pdf_path))
        except Exception:  # noqa: BLE001
            pass
    if res.cover_letter:
        (out / "cover_letter.txt").write_text(res.cover_letter.text)
    (out / "report.json").write_text(res.model_dump_json(indent=1, exclude={"resume": {"content"}}))
