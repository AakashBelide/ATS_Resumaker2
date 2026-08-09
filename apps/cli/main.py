"""resumaker CLI - a thin, dependency-light wrapper over the library.

    uv run python -m apps.cli run <jd_url> [--out DIR] [--pages N] [--gate]
                                           [--semantic lexical|gemini] [--no-parallel]
                                           [--no-cover] [--json] [--plain]
    uv run python -m apps.cli watch <out_dir>          # live view of a running run
    uv run python -m apps.cli ingest <source> <token>  # list+dedupe a board's postings
    uv run python -m apps.cli costs                     # LLM spend + Gemini budget
    uv run python -m apps.cli serve [--port N]          # launch the API

`run` shows a live per-stage table (rich); `watch` renders the same from status.json so a
detached/background run is observable from another terminal.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from resumaker.domain import PipelineResult
from resumaker.observability.cost import summary as cost_summary
from resumaker.pipeline import run_pipeline

_ICON = {"start": "*", "done": "OK", "skip": "--", "error": "XX"}
_MARK = {"start": "[yellow]... [/]", "done": "[green]OK[/]",
         "skip": "[dim]skip[/]", "error": "[red]XX[/]"}


def _printer(stage: str, status: str, detail: str = "") -> None:
    if status == "start":
        print(f"  [ ..] {stage} ...", flush=True)
    else:
        print(f"  [{_ICON.get(status, '  '):>3}] {stage} {detail}".rstrip(), flush=True)


def _stage_table(stages: list[dict], title: str):
    from rich.table import Table
    t = Table(title=title, expand=False)
    t.add_column("stage", style="cyan", no_wrap=True)
    t.add_column("status")
    t.add_column("elapsed", justify="right")
    t.add_column("detail", style="dim", overflow="fold", max_width=60)
    for s in stages:
        el = f"{s['elapsed']}s" if s.get("elapsed") is not None else ""
        t.add_row(s["stage"], _MARK.get(s["status"], s["status"]), el, s.get("detail", "") or "")
    return t


class _LiveProgress:
    """Drives a rich Live table from orchestrator on_progress callbacks (foreground)."""

    def __init__(self, title: str):
        from rich.console import Console
        from rich.live import Live
        self.title = title
        self.stages: dict[str, dict] = {}
        self.order: list[str] = []
        self._live = Live(console=Console(), refresh_per_second=8, transient=False)

    def __enter__(self):
        self._live.start()
        return self

    def __exit__(self, *exc):
        self._live.stop()

    def __call__(self, stage: str, status: str, detail: str = "") -> None:
        if stage not in self.stages:
            self.order.append(stage)
        el = None
        if status != "start" and detail.endswith("s") and detail[:-1].replace(".", "").isdigit():
            el = float(detail[:-1])
        prev = self.stages.get(stage, {})
        self.stages[stage] = {"stage": stage, "status": status,
                              "elapsed": el if el is not None else prev.get("elapsed"),
                              "detail": detail if status != "done" else prev.get("detail", "")}
        self._live.update(_stage_table([self.stages[s] for s in self.order], self.title))


def _summary(res: PipelineResult) -> None:
    if res.error or res.job is None:
        print(f"\nERROR: {res.error or 'no job produced'}")
        return
    j = res.job
    print("\n" + "=" * 68)
    print(f"ROLE: {j.title} @ {j.company}  ({j.location or '?'}, {j.work_model.value})")
    if res.fit:
        print(f"FIT : {res.fit.final_0_100}/100 ({res.fit.final_1_5}/5)   "
              f"[det={res.fit.deterministic_0_100} llm={res.fit.llm_0_100}]")
    sp = res.sponsorship or {}
    print(f"SPONSORSHIP: {sp.get('verdict','?')} (source={sp.get('source','?')})")
    if res.decision:
        print(f"APPLY: {'YES' if res.decision.recommend_apply else 'NO'} "
              f"(confidence={res.decision.confidence})")
        for b in res.decision.blockers:
            print(f"   BLOCKER: {b}")
    if res.gated_out:
        print("\n(gated out - resume/cover skipped)")
    if res.resume:
        fg = "PASS" if res.fact_gate and res.fact_gate.passed else "BLOCKED"
        av = "PASS" if res.ats_verify and res.ats_verify.passed else "BLOCKED"
        print(f"\nRESUME: {res.resume.pdf_path}")
        print(f"  pages={res.resume.page_count}  fact-gate={fg}  ATS-verify={av}")
        if res.ats:
            print(f"  ATS(proxy) {res.ats.overall_0_100}/100 [{res.ats.band}]  "
                  f"kw={res.ats.keyword_coverage} quant={res.ats.quantification} "
                  f"struct={res.ats.structure} semantic={res.ats.semantic_coverage}%")
            if res.ats.missing_keywords:
                print(f"  missing keywords: {', '.join(res.ats.missing_keywords[:8])}")
        if res.ats_verify and res.ats_verify.warnings:
            for w in res.ats_verify.warnings:
                print(f"  verify-warning: {w}")
    if res.cover_letter:
        print(f"\nCOVER LETTER: {res.cover_letter.word_count} words  "
              f"grounded={res.cover_letter.passed}")
        for w in res.cover_letter.warnings:
            print(f"  cl-warning: {w}")
    for w in res.warnings:
        print(f"\nWARNING: {w}")
    if res.out_dir:
        print(f"\nArtifacts: {res.out_dir}")
    if res.timings:
        print("Timings(s):", dict(res.timings.items()))


def _run_kwargs(args) -> dict:
    return {"out_dir": args.out, "target_pages": args.pages, "gate": args.gate,
            "parallel": not args.no_parallel, "make_cover_letter": not args.no_cover,
            "semantic_method": args.semantic}


def _cmd_run(args) -> int:
    print(f"Running pipeline for: {args.url}\n")
    use_live = not args.plain and not args.json and sys.stdout.isatty()
    if use_live:
        try:
            with _LiveProgress(f"pipeline: {args.url}") as live:
                res = run_pipeline(args.url, on_progress=live, **_run_kwargs(args))
        except Exception:  # noqa: BLE001 - rich unavailable/no tty -> fall back
            res = run_pipeline(args.url, on_progress=_printer, **_run_kwargs(args))
    else:
        res = run_pipeline(args.url, on_progress=_printer, **_run_kwargs(args))
    if args.json:
        print(res.model_dump_json(indent=1, exclude={"resume": {"content"}}))
    else:
        _summary(res)
    return 1 if res.error else 0


def _cmd_watch(args) -> int:
    """Poll a run's status.json and render a live table (for background runs)."""
    from rich.live import Live
    status = Path(args.dir) / "status.json"
    print(f"Watching {status} (Ctrl-C to stop)\n")
    with Live(refresh_per_second=4) as live:
        for _ in range(args.timeout * 2):
            if status.exists():
                snap = json.loads(status.read_text())
                title = f"{snap.get('url','') or args.dir}  ({snap.get('elapsed',0)}s)"
                live.update(_stage_table(snap.get("stages", []), title))
                if snap.get("done"):
                    break
            time.sleep(0.5)
    return 0


def _cmd_ingest(args) -> int:
    """List a board's postings and dedupe them into the jobs index."""
    from resumaker.domain import BoardRef, Company
    from resumaker.ingestion import ingest_company
    from resumaker.persistence import db
    db.init_db()
    company = Company(name=args.token, boards=[BoardRef(source=args.source, token=args.token)])
    r = ingest_company(company)
    print(f"{args.source}/{args.token}: {r.new} new/changed, {r.unchanged} unchanged"
          + (f"  errors={r.errors}" if r.errors else ""))
    return 0


def _cmd_onboard(args) -> int:
    """Auto-discover a company's board and (optionally) add it to the watchlist."""
    from resumaker.domain import Company
    from resumaker.ingestion import resolve
    from resumaker.persistence import db
    db.init_db()
    res = resolve(args.name, careers_url=args.careers_url)
    if res.resolved:
        b = res.boards[0]
        print(f"RESOLVED {args.name!r} via {res.method}: {b.source}/{b.token}"
              + (f" {b.extra}" if b.extra else ""))
        if not args.no_add:
            db.add_company(Company(name=args.name, boards=res.boards))
            print("  -> added to watchlist")
    else:
        print(f"UNRESOLVED {args.name!r}: {res.note}")
        if res.tried:
            print(f"  tried: {', '.join(res.tried)}")
    return 0 if res.resolved else 2


def _cmd_onboard_seed(args) -> int:
    """Onboard every company in a JSON list ([\"Name\", ...] or [{name, careers_url?}]).
    Prints a resolved/manual report; adds resolved companies to the watchlist."""
    from resumaker.domain import Company
    from resumaker.ingestion import resolve
    from resumaker.persistence import db
    db.init_db()
    items = json.loads(Path(args.file).read_text())
    entries = [{"name": i} if isinstance(i, str) else i for i in items]
    resolved, manual = [], []
    for e in entries:
        res = resolve(e["name"], careers_url=e.get("careers_url"))
        if res.resolved:
            db.add_company(Company(name=e["name"], boards=res.boards))
            b = res.boards[0]
            resolved.append((e["name"], f"{b.source}/{b.token}", res.method))
            print(f"  [OK]     {e['name']:28} {b.source}/{b.token}  ({res.method})", flush=True)
        else:
            manual.append(e["name"])
            print(f"  [MANUAL] {e['name']:28} needs careers_url/token", flush=True)
    print(f"\nResolved {len(resolved)}/{len(entries)}; {len(manual)} need manual onboarding.")
    if manual:
        print("Manual:", ", ".join(manual))
    return 0


def _cmd_schedule(args) -> int:
    """Run the watchlist poll once (--once) or start the recurring scheduler (blocking)."""
    from resumaker.ingestion.scheduler import run_tick
    if args.once:
        results = run_tick()
        total_new = sum(r.new for r in results)
        print(f"tick: {len(results)} companies, {total_new} new/changed postings")
        return 0
    from apscheduler.schedulers.blocking import BlockingScheduler

    from resumaker.config import get_settings
    sched = BlockingScheduler()
    mins = get_settings().scheduler_interval_minutes
    sched.add_job(run_tick, "interval", minutes=mins, id="watchlist_ingest")
    print(f"scheduler running every {mins} min (Ctrl-C to stop)")
    import contextlib
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        sched.start()
    return 0


def _cmd_costs(_args) -> int:
    print(json.dumps(cost_summary(), indent=1))
    return 0


def _cmd_serve(args) -> int:
    import uvicorn

    from resumaker.config import get_settings
    s = get_settings()
    uvicorn.run("apps.api.main:app", host=s.api_host, port=args.port or s.api_port,
                reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="resumaker", description="ATS resume pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the full pipeline on a JD URL")
    r.add_argument("url")
    r.add_argument("--out", default=None, help="output directory")
    r.add_argument("--pages", type=int, default=1, help="target page count (1 or 2)")
    r.add_argument("--gate", action="store_true", help="skip resume if apply-decision is negative")
    r.add_argument("--no-parallel", action="store_true", help="run analyses sequentially")
    r.add_argument("--no-cover", action="store_true", help="skip the cover letter")
    r.add_argument("--semantic", choices=["lexical", "gemini"], default="lexical")
    r.add_argument("--json", action="store_true", help="print the full result as JSON")
    r.add_argument("--plain", action="store_true", help="plain text progress (no live table)")
    r.set_defaults(func=_cmd_run)

    w = sub.add_parser("watch", help="live-view a run's progress from its status.json")
    w.add_argument("dir", help="the run's output directory (contains status.json)")
    w.add_argument("--timeout", type=int, default=600, help="max seconds to watch")
    w.set_defaults(func=_cmd_watch)

    g = sub.add_parser("ingest", help="list+dedupe a company board's postings into jobs")
    g.add_argument("source", help="board source, e.g. greenhouse")
    g.add_argument("token", help="board token/slug, e.g. databricks")
    g.set_defaults(func=_cmd_ingest)

    o = sub.add_parser("onboard", help="auto-discover a company's board + add to watchlist")
    o.add_argument("name", help="company name, e.g. 'State Street'")
    o.add_argument("--careers-url", default=None, help="careers page URL (helps resolve Workday/custom)")
    o.add_argument("--no-add", action="store_true", help="just report; don't add to the watchlist")
    o.set_defaults(func=_cmd_onboard)

    os_ = sub.add_parser("onboard-seed", help="onboard every company in a JSON list; report resolved/manual")
    os_.add_argument("file", help="JSON list of company names (or {name, careers_url} objects)")
    os_.set_defaults(func=_cmd_onboard_seed)

    sc = sub.add_parser("schedule", help="poll the watchlist (--once) or run the recurring scheduler")
    sc.add_argument("--once", action="store_true", help="run a single ingest tick and exit")
    sc.set_defaults(func=_cmd_schedule)

    c = sub.add_parser("costs", help="show LLM spend (Gemini budget + Claude usage)")
    c.set_defaults(func=_cmd_costs)

    sv = sub.add_parser("serve", help="launch the API (uvicorn)")
    sv.add_argument("--port", type=int, default=None)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=_cmd_serve)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
