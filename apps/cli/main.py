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


def _cmd_discovery(args) -> int:
    """Filterable, LLM-free view over the ingested feed (RA.1). No resume scoring."""
    from resumaker.ingestion import DiscoveryFilters, discover
    from resumaker.persistence import db
    db.init_db()
    res = discover(DiscoveryFilters(
        company=[args.company] if args.company else None, source=args.source,
        location=args.location, keyword=args.keyword, since_days=args.since_days,
        on_target=args.on_target, order=args.order, limit=args.limit, offset=args.offset))
    if args.json:
        print(json.dumps({"total": res.total, "facets": res.facets,
                          "jobs": [j.model_dump(mode="json") for j in res.jobs]}, indent=1))
        return 0
    shown = f"{len(res.jobs)} of {res.total}"
    print(f"DISCOVERY - {shown} postings"
          + (f"  (offset {args.offset})" if args.offset else "") + "\n")
    for j in res.jobs:
        seen = (j.first_seen.date().isoformat() if j.first_seen else "")
        print(f"  {seen}  {j.title[:52]:52}  {j.company[:18]:18}  {j.location[:24]}")
    top = sorted(res.facets.get("companies", {}).items(), key=lambda x: -x[1])[:8]
    if top:
        print("\nby company:", ", ".join(f"{c}({n})" for c, n in top))
    return 0


def _fmt_tracked(e) -> str:
    fit = f"{e.fit_0_100:.0f}" if e.fit_0_100 is not None else "--"
    app = "" if e.recommend_apply is None else ("apply" if e.recommend_apply else "skip")
    return (f"  #{e.id:<4} [{e.stage:10}] fit={fit:>3} {app:5} "
            f"{e.title[:40]:40} {e.company[:16]:16} {e.sponsorship}")


def _cmd_track_add(args) -> int:
    """Add a job to the tracker; runs the match pipeline (fit/gap/sponsorship, no resume)."""
    from resumaker.ingestion import tracker
    from resumaker.persistence import db
    db.init_db()
    if not args.no_match:
        print("Running match (scrape -> structure -> keywords|gap|sponsorship -> fit -> apply)...")
    try:
        e = tracker.add(job_id=args.job_id, url=args.url, run_match=not args.no_match)
    except tracker.TrackerError as err:
        print(f"ERROR: {err}")
        return 2
    print("Tracked:\n" + _fmt_tracked(e))
    if e.run_id:
        print(f"  match artifacts: outputs/{e.run_id}/")
    return 0


def _cmd_track_list(args) -> int:
    from resumaker.ingestion import tracker
    from resumaker.persistence import db
    db.init_db()
    rows = tracker.list_tracked(stage=args.stage)
    print(f"TRACKER - {len(rows)} job(s)" + (f" in stage '{args.stage}'" if args.stage else ""))
    for e in rows:
        print(_fmt_tracked(e))
    return 0


def _cmd_track_stage(args) -> int:
    from resumaker.ingestion import tracker
    from resumaker.persistence import db
    db.init_db()
    try:
        e = tracker.set_stage(args.id, args.stage)
    except tracker.TrackerError as err:
        print(f"ERROR: {err}")
        return 2
    print(f"#{e.id} -> {e.stage}")
    return 0


def _cmd_track_note(args) -> int:
    from resumaker.ingestion import tracker
    from resumaker.persistence import db
    db.init_db()
    try:
        tracker.set_notes(args.id, args.text)
    except tracker.TrackerError as err:
        print(f"ERROR: {err}")
        return 2
    print(f"#{args.id} note saved")
    return 0


def _cmd_track_rm(args) -> int:
    from resumaker.ingestion import tracker
    from resumaker.persistence import db
    db.init_db()
    print(f"removed {tracker.remove(args.id)} entry")
    return 0


def _cmd_profile_show(_args) -> int:
    """Local, full view of the profile signals + preferences + enrichment log tail."""
    from resumaker.enrichment import preferences, read_enrichment_log
    from resumaker.persistence import profile
    prefs = preferences()
    print("PROFILE")
    print(f"  years_experience : {profile.candidate_years()}")
    print(f"  needs_sponsorship: {profile.needs_sponsorship()}")
    print(f"  employers        : {', '.join(sorted(profile.all_employers()))}")
    print(f"  titles           : {', '.join(sorted(profile.all_titles()))}")
    print(f"  skills ({len(profile.all_skills())}):    {', '.join(sorted(profile.all_skills()))}")
    print("\nPREFERENCES")
    print(f"  target_roles: {prefs.get('target_roles', [])}")
    print(f"  avoid_roles : {prefs.get('avoid_roles', [])}")
    loc = prefs.get("location", {})
    if loc:
        print(f"  location    : {loc}")
    log = read_enrichment_log()[-5:]
    if log:
        print("\nRECENT ENRICHMENT LOG")
        for r in log:
            print(f"  {r.get('ts','')[:19]}  {r.get('kind','')}: {r.get('detail','')}")
    return 0


def _cmd_profile_set(args) -> int:
    """Fold an owner-provided fact into profile.json (path is dot/bracket, value is JSON)."""
    from resumaker.enrichment import update_profile_fact
    # path like "skills.Languages" or "preferences.location.base" -> list of keys
    path: list = []
    for seg in args.path.replace("]", "").replace("[", ".").split("."):
        if seg == "":
            continue
        path.append(int(seg) if seg.isdigit() else seg)
    try:
        value = json.loads(args.value)      # allow lists/objects/numbers
    except json.JSONDecodeError:
        value = args.value                  # plain string
    old = update_profile_fact(path, value, args.reason)
    print(f"set {args.path}: {old!r} -> {value!r}\n  reason: {args.reason}")
    return 0


def _cmd_profile_proposals(_args) -> int:
    """Enrichment proposals mined from tracked jobs' gap reports (owner approves manually)."""
    from resumaker.enrichment import propose_from_tracker, tracked_report_count
    n = tracked_report_count()
    props = propose_from_tracker()
    print(f"ENRICHMENT PROPOSALS  (from {n} tracked match report(s))\n")
    have = props["have_but_unlisted"]
    print(f"HAVE BUT UNLISTED (evidence exists; safe to add explicitly) - {len(have)}")
    for p in have:
        print(f"  [{p.count}x] {p.requirement[:70]}   ({', '.join(p.companies[:3])})")
    gaps = props["recurring_gaps"]
    print(f"\nRECURRING GAPS (verify you actually have it before adding) - {len(gaps)}")
    for p in gaps:
        print(f"  [{p.count}x] {p.requirement[:70]}   ({', '.join(p.companies[:3])})")
    if not have and not gaps:
        print("  (none yet - track some jobs first: `track add`)")
    return 0


def _cmd_remove(args) -> int:
    """Remove a company from the watchlist."""
    from resumaker.persistence import db
    n = db.remove_company(args.name)
    print(f"removed {n} row(s) for {args.name!r}")
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


def _cmd_dashboard(args) -> int:
    """Feed + application-funnel stats (RA.4). Deterministic, $0."""
    from resumaker.analytics import dashboard_stats
    from resumaker.persistence import db
    db.init_db()
    s = dashboard_stats(days=args.days)
    if args.json:
        print(json.dumps(s, indent=1))
        return 0
    w = s["watchlist"]
    print(f"WATCHLIST: {w['companies']} companies, {w['jobs']} postings, {w['tracked']} tracked\n")
    print(f"NEW LISTINGS (last {args.days}d):")
    for d in s["new_listings_daily"][:args.days]:
        print(f"  {d['date']}  {'#' * min(d['count'], 60)} {d['count']}")
    print("\nTOP COMPANIES:", ", ".join(f"{c}({n})" for c, n in
                                        list(s["jobs_by_company"].items())[:10]))
    print("BY SOURCE:", ", ".join(f"{c}({n})" for c, n in s["jobs_by_source"].items()))
    if s["tracker_funnel"]:
        print("\nAPPLICATION FUNNEL:", ", ".join(f"{k}={v}" for k, v in
                                                 s["tracker_funnel"].items()))
    r = s["runs"]
    print(f"\nRUNS: {r['total']} total {r['by_status']}  "
          f"avg_fit={r['avg_fit']} avg_ats={r['avg_ats']} cost=${r['total_cost_usd']}")
    return 0


def _cmd_metrics(args) -> int:
    """Model calls / cost / usage (RA.5)."""
    from resumaker.analytics import metrics_overview
    from resumaker.persistence import db
    db.init_db()
    ov = metrics_overview()
    if args.json:
        print(json.dumps(ov, indent=1))
        return 0
    print("LLM USAGE (by provider):")
    for prov, a in ov["cost"].items():
        if prov.startswith("_"):
            continue
        print(f"  {prov:12} calls={a['calls']:4} in={a['input_tokens']:>8} "
              f"out={a['output_tokens']:>8} cost=${a['cost_usd']}")
    gb = ov["cost"].get("_gemini_budget", {})
    if gb:
        print(f"  gemini budget: ${gb['spent_usd']} / ${gb['cap_usd']} "
              f"(remaining ${gb['remaining_usd']})")
    r = ov["runs"]
    print(f"\nRUNS: {r['total']} {r['by_status']}  cost=${r['total_cost_usd']}")
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

    dc = sub.add_parser("discovery", help="filterable feed of ingested postings (no LLM/scoring)")
    dc.add_argument("--company", default=None)
    dc.add_argument("--source", default=None)
    dc.add_argument("--location", default=None, help="location substring, e.g. boston")
    dc.add_argument("--keyword", default=None, help="title substring, e.g. 'machine learning'")
    dc.add_argument("--since-days", type=int, default=None, dest="since_days")
    dc.add_argument("--on-target", action="store_true", dest="on_target",
                    help="only titles matching your target roles (and not avoid roles)")
    dc.add_argument("--order", choices=["recent", "company", "title"], default="recent")
    dc.add_argument("--limit", type=int, default=50)
    dc.add_argument("--offset", type=int, default=0)
    dc.add_argument("--json", action="store_true")
    dc.set_defaults(func=_cmd_discovery)

    tk = sub.add_parser("track", help="tracker: jobs you're pursuing (add runs the match)")
    tksub = tk.add_subparsers(dest="track_cmd", required=True)
    ta = tksub.add_parser("add", help="add a job (--job-id from discovery, or --url)")
    ta.add_argument("--job-id", type=int, default=None, dest="job_id")
    ta.add_argument("--url", default=None)
    ta.add_argument("--no-match", action="store_true", help="skip the match run (just track)")
    ta.set_defaults(func=_cmd_track_add)
    tl = tksub.add_parser("list", help="list tracked jobs")
    tl.add_argument("--stage", default=None)
    tl.set_defaults(func=_cmd_track_list)
    ts = tksub.add_parser("stage", help="advance a job's application stage")
    ts.add_argument("id", type=int)
    ts.add_argument("stage", help="interested|applied|interview|offer|rejected|skipped")
    ts.set_defaults(func=_cmd_track_stage)
    tn = tksub.add_parser("note", help="set notes on a tracked job")
    tn.add_argument("id", type=int)
    tn.add_argument("text")
    tn.set_defaults(func=_cmd_track_note)
    tr = tksub.add_parser("rm", help="remove a tracked job")
    tr.add_argument("id", type=int)
    tr.set_defaults(func=_cmd_track_rm)

    pf = sub.add_parser("profile", help="view/edit your profile + enrichment proposals")
    pfsub = pf.add_subparsers(dest="profile_cmd", required=True)
    pfsub.add_parser("show", help="full local view of profile + preferences").set_defaults(
        func=_cmd_profile_show)
    ps = pfsub.add_parser("set", help="update a profile fact (path=dot/bracket, value=JSON)")
    ps.add_argument("path", help="e.g. skills.Languages or preferences.location.base")
    ps.add_argument("value", help="JSON value (list/obj/number) or plain string")
    ps.add_argument("--reason", required=True, help="why (audited in the enrichment log)")
    ps.set_defaults(func=_cmd_profile_set)
    pfsub.add_parser("proposals", help="enrichment ideas mined from tracked jobs").set_defaults(
        func=_cmd_profile_proposals)

    rm = sub.add_parser("remove", help="remove a company from the watchlist")
    rm.add_argument("name", help="company name (exact)")
    rm.set_defaults(func=_cmd_remove)

    sc = sub.add_parser("schedule", help="poll the watchlist (--once) or run the recurring scheduler")
    sc.add_argument("--once", action="store_true", help="run a single ingest tick and exit")
    sc.set_defaults(func=_cmd_schedule)

    c = sub.add_parser("costs", help="show LLM spend (Gemini budget + Claude usage)")
    c.set_defaults(func=_cmd_costs)

    db_ = sub.add_parser("dashboard", help="feed + application-funnel stats")
    db_.add_argument("--days", type=int, default=14)
    db_.add_argument("--json", action="store_true")
    db_.set_defaults(func=_cmd_dashboard)

    mt = sub.add_parser("metrics", help="model calls / cost / usage overview")
    mt.add_argument("--json", action="store_true")
    mt.set_defaults(func=_cmd_metrics)

    sv = sub.add_parser("serve", help="launch the API (uvicorn)")
    sv.add_argument("--port", type=int, default=None)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=_cmd_serve)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
