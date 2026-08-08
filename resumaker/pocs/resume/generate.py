"""Resume generation orchestrator (Task 1.8).

job (structured) -> [keywords, gap] -> grounded tailoring -> ATS-safe .docx -> PDF.
Returns a ResumeDoc with artifact paths + page count. Verification (fact-gate 1.9,
ATS-parse 1.10) runs as separate stages on this output.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.schemas import GapReport, JobPosting, KeywordSet, ResumeContent, ResumeDoc
from pocs.gap import analyze_gaps
from pocs.keywords import extract_keywords
from pocs.resume.render_docx import render_docx
from pocs.resume.render_pdf import docx_to_pdf, page_count
from pocs.resume.tailor import tailor_resume

_OUT = Path(__file__).resolve().parents[3] / "outputs"


def _slug(*parts: str) -> str:
    s = "-".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")[:60] or "resume"


def _skills_count(content: ResumeContent) -> int:
    return sum(len(v) for v in content.skills.values())


def _combine_dates(newer: str, older: str) -> str:
    """Merge 'start - end' ranges (list is newest-first): older.start - newer.end."""
    def parts(d):
        bits = [x.strip() for x in re.split(r"\s*[-–]\s*", d) if x.strip()]
        return (bits[0], bits[-1]) if bits else ("", "")
    n_start, n_end = parts(newer)
    o_start, _ = parts(older)
    return f"{o_start or n_start} - {n_end or ''}".strip(" -")


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _end_key(dates: str) -> tuple[int, int]:
    """Sort key from the END of a 'start - end' range (reverse-chronological)."""
    end = re.split(r"\s*[-–]\s*", dates or "")[-1].strip().lower()
    if any(w in end for w in ("present", "current", "now")):
        return (9999, 12)
    mon = next((_MONTHS[k] for k in _MONTHS if k in end), 0)
    ym = re.search(r"(19|20)\d{2}", end)
    return (int(ym.group(0)) if ym else 0, mon)


def _sort_reverse_chron(exps: list[dict]) -> list[dict]:
    return sorted(exps, key=lambda e: _end_key(e.get("dates", "")), reverse=True)


def _merge_same_company(exps: list[dict]) -> list[dict]:
    """Merge consecutive roles at the SAME company into one block showing the
    promotion (oldest title -> newest title), the full date range, and merged
    bullets. Recruiters read this as growth; it also saves header lines."""
    if not exps:
        return exps
    groups: list[list[dict]] = [[dict(exps[0])]]
    for e in exps[1:]:
        same = e.get("organization", "").strip().lower() == \
            groups[-1][-1].get("organization", "").strip().lower()
        (groups[-1] if same else groups).append(dict(e)) if same else groups.append([dict(e)])
    out: list[dict] = []
    for g in groups:
        if len(g) == 1:
            out.append(g[0]); continue
        newest, oldest = g[0], g[-1]
        # Fallback title = the SHORTEST real title in the group (tends to be the
        # clean core engineering title, avoiding verbose unit/management titles).
        # The tailorer normally combines JD-aware already, so this rarely fires.
        title = min((x.get("title", "") for x in g if x.get("title")),
                    key=len, default=newest.get("title", ""))
        dates = _combine_dates(newest.get("dates", ""), oldest.get("dates", ""))
        bullets: list[str] = []
        for x in g:
            for b in x.get("bullets", []):
                if b not in bullets:
                    bullets.append(b)
        out.append({"title": title, "organization": newest.get("organization", ""),
                    "location": newest.get("location", ""), "dates": dates,
                    "bullets": bullets})
    return out


def _trim_one(content: ResumeContent) -> bool:
    """Shrink by one step, least-relevant first. PROJECTS are protected (tech
    differentiator) - trimmed only as a near-last resort, after oldest experience."""
    # 1) oversized skills -> drop last item of the largest category
    if _skills_count(content) > 26:
        cat = max(content.skills, key=lambda k: len(content.skills[k]))
        if content.skills[cat]:
            content.skills[cat].pop()
            if not content.skills[cat]:
                del content.skills[cat]
            return True
    # 2) trim OLDEST experiences first, PROTECTING the top-2 recent roles at >=2
    #    bullets (their highest-impact wins must survive).
    for i in range(len(content.experiences) - 1, -1, -1):
        floor = 2 if i < 2 else 1
        if len(content.experiences[i].get("bullets", [])) > floor:
            content.experiences[i]["bullets"].pop()
            return True
    # 3) drop the oldest experience if we still have >3 blocks
    if len(content.experiences) > 3:
        content.experiences.pop()
        return True
    # 4) trim projects (keep at least one project with one bullet)
    if content.projects:
        last = content.projects[-1]
        if len(last.get("bullets", [])) > 1:
            last["bullets"].pop()
        elif len(content.projects) > 1:
            content.projects.pop()
        else:
            return False
        return True
    # 5) absolute last resort: let the top-2 roles drop to 1 bullet
    for i in range(min(2, len(content.experiences))):
        if len(content.experiences[i].get("bullets", [])) > 1:
            content.experiences[i]["bullets"].pop()
            return True
    return False


def _apply_budget(content: ResumeContent, target_pages: int) -> None:
    """Fast, render-free pre-trim so content is already near the page budget
    (the render loop then fine-tunes). For a 1-page target: cap skills, roles,
    and bullets-per-role by recency."""
    if target_pages > 1:
        return
    # keep JD-relevant skills generous (only trim a truly oversized block)
    while _skills_count(content) > 30 and content.skills:
        cat = max(content.skills, key=lambda k: len(content.skills[k]))
        content.skills[cat].pop()
        if not content.skills[cat]:
            del content.skills[cat]
    # keep the 4 most relevant roles; fill with bullets (top roles get more depth)
    content.experiences = content.experiences[:4]
    caps = [4, 4, 3, 3]
    for e, cap in zip(content.experiences, caps):
        e["bullets"] = e.get("bullets", [])[:cap]
    # keep up to 2 projects (protected differentiator), 2 bullets each
    content.projects = content.projects[:2]
    for pr in content.projects:
        pr["bullets"] = pr.get("bullets", [])[:2]


def _fit_pages(content: ResumeContent, out: Path, slug: str,
               target_pages: int, max_iter: int = 20) -> tuple[str, str, int]:
    """Budget-trim, render, then deterministically fine-trim until <= target_pages."""
    _apply_budget(content, target_pages)
    docx = render_docx(content, str(out / f"{slug}.docx"))
    pdf = docx_to_pdf(docx)
    pages = page_count(pdf)
    it = 0
    while pages > target_pages and it < max_iter and _trim_one(content):
        docx = render_docx(content, str(out / f"{slug}.docx"))
        pdf = docx_to_pdf(docx)
        pages = page_count(pdf)
        it += 1
    return docx, pdf, pages


def generate_resume(job: JobPosting, *, keyword_set: KeywordSet | None = None,
                    gap: GapReport | None = None, tailor_model: str = "opus",
                    target_pages: int = 1, out_dir: str | None = None) -> ResumeDoc:
    keyword_set = keyword_set or extract_keywords(job)
    gap = gap or analyze_gaps(job)
    content = tailor_resume(job, keyword_set, gap, model=tailor_model)
    # combine consecutive same-company roles, then enforce reverse-chronological order
    content.experiences = _sort_reverse_chron(_merge_same_company(content.experiences))

    slug = _slug(job.company, job.title)
    out = Path(out_dir) if out_dir else _OUT / slug
    docx, pdf, pages = _fit_pages(content, out, slug, target_pages)
    return ResumeDoc(content=content, docx_path=docx, pdf_path=pdf, page_count=pages)


if __name__ == "__main__":
    import sys
    from pocs.jd_structure import structure_jd
    from pocs.scrape_jd import scrape
    job = structure_jd(scrape(sys.argv[1]))
    doc = generate_resume(job)
    print(f"# {job.title} @ {job.company}")
    print("docx:", doc.docx_path)
    print("pdf :", doc.pdf_path, "| pages:", doc.page_count)
    print("headline:", doc.content.headline)
    print("summary:", doc.content.summary[:200])
    print("experiences:", [e.get("organization") for e in doc.content.experiences])
