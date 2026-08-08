"""Phase-2 preview: full pipeline on one JD URL, with the fit/apply gate shown.
Usage: uv run python run_pipeline.py <jd_url>
"""
import json
import sys
from pathlib import Path

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

url = sys.argv[1]
job = structure_jd(scrape(url), model="sonnet")
ks = extract_keywords(job)
gap = analyze_gaps(job)
fit = score_fit(job, gap=gap)
sig = sponsor_signal(job.company) if job.company else None
verdict = resolve_sponsorship(job, sig)
decision = decide_apply(job, fit, verdict)

print("=" * 70)
print(f"ROLE: {job.title} @ {job.company}  ({job.location}, {job.work_model.value})")
print(f"seniority={job.seniority}  sponsorship_stance={job.sponsorship_stance}")
print(f"\nROLE-FIT: {fit.final_0_100}/100 ({fit.final_1_5}/5)  "
      f"[det={fit.deterministic_0_100} llm={fit.llm_0_100}]")
print("  dims:", {k: int(v) for k, v in fit.dimensions.items()})
print("  why:", fit.rationale)
print(f"\nSPONSORSHIP: {verdict.verdict} (source={verdict.source}, "
      f"needs_verification={verdict.needs_verification})")
for r in verdict.reasons:
    print("   -", r)
print(f"\nAPPLY DECISION: {'APPLY' if decision.recommend_apply else 'DO NOT APPLY'} "
      f"(confidence={decision.confidence})")
for b in decision.blockers:
    print("   BLOCKER:", b)
for r in decision.reasons:
    print("   -", r)

# Generate the resume regardless (so we can inspect quality), reusing ks+gap.
doc = generate_resume(job, keyword_set=ks, gap=gap)
rep = verify_resume(doc.content)
ats = score_ats(job, doc.content, keyword_set=ks)
vrep = verify_ats(job, doc.content, pdf_path=doc.pdf_path)
print(f"\nRESUME: {doc.pdf_path}")
print(f"  pages={doc.page_count}  fact-gate={'PASS' if rep.passed else 'BLOCKED'} "
      f"blockers={rep.blockers}")
print(f"  ATS-verify={'PASS' if vrep.passed else 'BLOCKED'} "
      f"blockers={vrep.blockers}")
for w in vrep.warnings:
    print("   verify-warning:", w)
print(f"  ATS(proxy) {ats.overall_0_100}/100 [{ats.band}]  kw={ats.keyword_coverage} "
      f"quant={ats.quantification} struct={ats.structure} "
      f"semantic={ats.semantic_coverage}% ({ats.semantic_method})")
if ats.missing_keywords:
    print("  missing keywords:", ", ".join(ats.missing_keywords))
if ats.weak_requirements:
    print("  under-evidenced reqs:", "; ".join(ats.weak_requirements[:3]))
print("  experience blocks:", [e.get("title", "")[:40] for e in doc.content.experiences])
print("  projects:", [p.get("title", "")[:30] for p in doc.content.projects])

# Cover letter (grounded, anti-AI-tell; human reviews before sending)
cl = write_cover_letter(job, gap=gap)
print(f"\nCOVER LETTER: {cl.word_count} words  grounded={cl.passed}")
for w in cl.warnings:
    print("   cl-warning:", w)

# Save readable artifacts next to the resume
out = Path(doc.pdf_path).parent
(out / "cover_letter.txt").write_text(cl.text)
(out / "JD.txt").write_text(f"{url}\n\n{job.raw_text}")
(out / "resume_extracted_text.txt").write_text(extract_text(doc.pdf_path))
(out / "content.json").write_text(doc.content.model_dump_json(indent=1))  # for free re-renders
(out / "report.json").write_text(json.dumps({
    "role": f"{job.title} @ {job.company}",
    "fit": fit.model_dump(), "sponsorship": verdict.__dict__,
    "decision": decision.model_dump(),
    "pages": doc.page_count, "fact_gate_passed": rep.passed,
    "ats": ats.model_dump(), "ats_verify": vrep.model_dump(),
    "cover_letter": {"word_count": cl.word_count, "passed": cl.passed,
                     "warnings": cl.warnings},
}, indent=1, default=str))
print("PIPELINE_DONE")
