"""Resumaker CLI (Phase 2).

    uv run python -m cli run <jd_url> [--out DIR] [--pages N] [--gate]
                                      [--semantic lexical|gemini] [--no-parallel]
                                      [--no-cover] [--json]
    uv run python -m cli costs

Streams stage progress, then prints a decision + resume + ATS + cover-letter summary.
"""
from __future__ import annotations

import argparse
import sys

from core.cost_guard import summary as cost_summary
from core.schemas import PipelineResult
from orchestrator import run_pipeline

_ICON = {"start": "*", "done": "OK", "skip": "--", "error": "XX"}


def _printer(stage: str, status: str, detail: str = "") -> None:
    if status == "start":
        print(f"  [ ..] {stage} ...", flush=True)
    else:
        print(f"  [{_ICON.get(status, '  '):>3}] {stage} {detail}".rstrip(), flush=True)


def _summary(res: PipelineResult) -> None:
    if res.error:
        print(f"\nERROR: {res.error}")
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
        print("Timings(s):", {k: v for k, v in res.timings.items()})


def _cmd_run(args) -> int:
    print(f"Running pipeline for: {args.url}\n")
    res = run_pipeline(
        args.url, out_dir=args.out, target_pages=args.pages, gate=args.gate,
        parallel=not args.no_parallel, make_cover_letter=not args.no_cover,
        semantic_method=args.semantic, on_progress=_printer)
    if args.json:
        print(res.model_dump_json(indent=1, exclude={"resume": {"content"}}))
    else:
        _summary(res)
    return 1 if res.error else 0


def _cmd_costs(_args) -> int:
    import json
    print(json.dumps(cost_summary(), indent=1))
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
    r.set_defaults(func=_cmd_run)

    c = sub.add_parser("costs", help="show LLM spend (Gemini budget + Claude usage)")
    c.set_defaults(func=_cmd_costs)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
