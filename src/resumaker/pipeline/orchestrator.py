"""Pipeline orchestrator: chain every stage into one call (blueprint 16/19).

Deterministic mechanics stay in code; cognitive stages are the `resumaker.stages`
modules. After structuring the JD, the three independent analyses (keywords, gap,
sponsorship) run as a PARALLEL fan-out. A ProgressReporter streams stage status (feeds
the CLI live view and the API's SSE endpoint). Each run is indexed in SQLite (`runs`)
for history/analytics; artifacts under the run dir stay canonical.

    from resumaker.pipeline import run_pipeline
    result = run_pipeline("https://boards.greenhouse.io/.../jobs/123")
"""
from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from resumaker.ats import score_ats
from resumaker.ats.fact_gate import verify_resume
from resumaker.ats.verify import verify_ats
from resumaker.domain import PipelineResult, RunRecord
from resumaker.observability import metrics
from resumaker.observability.logging import get_logger
from resumaker.persistence import db, files
from resumaker.pipeline.progress import ProgressReporter
from resumaker.pipeline.stage import run_stage
from resumaker.providers.scrape import scrape
from resumaker.stages.apply_decision import decide_apply
from resumaker.stages.cover_letter import write_cover_letter
from resumaker.stages.gap import analyze_gaps
from resumaker.stages.keywords import extract_keywords
from resumaker.stages.resume import generate_resume
from resumaker.stages.resume.render_pdf import extract_text
from resumaker.stages.role_fit import score_fit
from resumaker.stages.sponsorship import sponsor_signal
from resumaker.stages.sponsorship.resolve import resolve_sponsorship
from resumaker.stages.structure import structure_jd

Progress = Callable[[str, str, str], None]
_log = get_logger("resumaker.pipeline")


def _noop(stage: str, status: str, detail: str = "") -> None:
    pass


def run_pipeline(url: str | None = None, *, job=None, out_dir: str | None = None,
                 run_id: str | None = None, target_pages: int = 1, gate: bool = False,
                 parallel: bool = True, make_cover_letter: bool = True,
                 semantic_method: str = "lexical",
                 on_progress: Progress | None = None) -> PipelineResult:
    """Run the full pipeline for one JD.

    url            : JD URL to scrape (skip if `job` is supplied).
    job            : a pre-structured JobPosting (skips scrape+structure; for tests).
    run_id         : stable id for this run (the API supplies one up front so SSE +
                     artifacts route immediately); defaults to the company-role slug.
    gate           : if True, stop before resume/cover when apply-decision is negative.
    parallel       : fan out keywords/gap/sponsorship concurrently.
    on_progress    : callback(stage, status, detail); status in start|done|skip|error.
    """
    db.init_db()
    p = on_progress or _noop
    timings: dict[str, float] = {}
    res = PipelineResult(url=url or "")

    reporter = ProgressReporter(
        url=url or "",
        on_event=lambda ev: p(ev.stage, ev.status,
                              ev.detail or (f"{ev.elapsed}s" if ev.elapsed else "")),
        out_dir=out_dir)
    # When the caller supplies a run_id we can resolve the out-dir before scraping, so
    # status.json exists from the first event (the API's SSE stream needs this).
    if reporter.out_dir is None and run_id:
        out_dir = out_dir or str(files.run_dir(run_id))
        reporter.set_out_dir(out_dir)

    def timed(stage, fn):
        return run_stage(reporter, stage, fn, timings)

    metrics.inc("resumaker_runs_total")
    try:
        # 1) scrape + structure (unless a job was passed in)
        if job is None:
            if not url:
                raise ValueError("run_pipeline requires `url` when `job` is not provided")
            raw = timed("scrape", lambda: scrape(url))
            job = timed("structure", lambda: structure_jd(raw, model="sonnet"))
        res.job = job

        # resolve the out-dir now so status.json + all artifacts land together
        slug = run_id or files.run_slug(job.company, job.title, fallback=url or "job")
        resolved_out = out_dir or str(files.run_dir(slug))
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
            timings["analyze"] = round(time.time() - t0, 2)
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
            res.timings = timings
            _save(res, url, job, out_dir)
            _index_run(slug, res, status="gated_out")
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
                res.cover_letter = timed("cover_letter",
                                         lambda: write_cover_letter(job, gap=gap))
            except Exception as e:  # noqa: BLE001
                res.warnings.append(f"cover_letter failed (resume is unaffected): {e}")

        res.timings = timings
        _save(res, url, job, out_dir)
        _index_run(slug, res, status="done")
        metrics.inc("resumaker_runs_total", status="done")
        return res
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"
        res.timings = timings
        metrics.inc("resumaker_runs_total", status="error")
        _log.warning("pipeline error", extra={"url": url, "error": res.error})
        reporter.emit("pipeline", "error", res.error)
        return res
    finally:
        reporter.finish()


def _save(res: PipelineResult, url: str | None, job, out_dir: str | None = None) -> None:
    """Write human-readable artifacts + a machine report.json next to the resume."""
    if res.resume and res.resume.pdf_path:
        out = Path(res.resume.pdf_path).parent
    elif out_dir:
        out = Path(out_dir)
    else:
        out = files.run_dir(files.run_slug(job.company, job.title, fallback=url or "job"))
    out.mkdir(parents=True, exist_ok=True)
    res.out_dir = str(out)

    files.write_text(out / "JD.txt", f"{url or ''}\n\n{job.raw_text}")
    if res.resume:
        files.write_text(out / "content.json", res.resume.content.model_dump_json(indent=1))
        with contextlib.suppress(Exception):
            files.write_text(out / "resume_extracted_text.txt",
                             extract_text(res.resume.pdf_path))
    if res.cover_letter:
        files.write_text(out / "cover_letter.txt", res.cover_letter.text)
    files.write_text(out / "report.json",
                     res.model_dump_json(indent=1, exclude={"resume": {"content"}}))


def _index_run(run_id: str, res: PipelineResult, *, status: str) -> None:
    """Upsert the run's queryable metadata into SQLite (files stay canonical)."""
    try:
        db.record_run(RunRecord(
            id=run_id, url=res.url, out_dir=res.out_dir, status=status,
            recommend_apply=(res.decision.recommend_apply if res.decision else None),
            fit_0_100=(res.fit.final_0_100 if res.fit else None),
            ats_overall=(res.ats.overall_0_100 if res.ats else None),
            fact_gate_pass=(res.fact_gate.passed if res.fact_gate else None),
            ats_verify_pass=(res.ats_verify.passed if res.ats_verify else None),
            page_count=(res.resume.page_count if res.resume else None),
            error=res.error, created_at=datetime.now(UTC),
            finished_at=datetime.now(UTC)))
    except Exception as e:  # noqa: BLE001 - indexing must never fail the run
        _log.warning("run indexing failed", extra={"run_id": run_id, "error": str(e)})
