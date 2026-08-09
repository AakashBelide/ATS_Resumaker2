"""Deterministic ATS scorer (blueprint 12) + semantic coverage (11).

Transparent, reproducible 0-100 = 0.5*keyword + 0.3*quantification + 0.2*structure,
plus a separate per-requirement semantic-coverage axis. This is an HONEST
keyword/skill-overlap proxy, NOT a prediction of any real (proprietary) ATS score.

Weights follow ATS-Resumaker's proven split; hard skills weigh more than soft
(Jobscan's approach). Quantification rewards the ~50-60% band, not 100% (blueprint
2: metric-in-every-bullet reads formulaic).
"""
from __future__ import annotations

import re

from resumaker.ats import semantic as sem
from resumaker.domain import ATSScore, JobPosting, KeywordSet, ResumeContent
from resumaker.persistence import profile as prof

_QUANT_RE = re.compile(
    r"(?<![A-Za-z0-9])\$?\d[\d,]*(?:\.\d+)?\s?\+?\s?"
    r"(?:%|x|k|m|b|million|billion|thousand|hours?|mins?|minutes?|users?|records?|"
    r"nodes?|edges?|logs?|days?|weeks?|months?|years?)?", re.I)
_UNIT = ("%", "$", "x", "million", "billion", "thousand", "hour", "min", "user",
         "record", "node", "edge", "log", "day", "week", "month", "year")
_MONYEAR = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(19|20)\d{2}", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _bullets(content: ResumeContent) -> list[str]:
    out: list[str] = []
    for e in content.experiences + content.projects:
        out += [str(b) for b in (e.get("bullets") or [])]
    return [b for b in out if b.strip()]


def _resume_text(content: ResumeContent) -> str:
    parts = [content.headline, content.summary]
    parts += _bullets(content)
    for cat, items in (content.skills or {}).items():
        parts.append(f"{cat}: " + ", ".join(items))
    return "\n".join(p for p in parts if p)


def _has_metric(text: str) -> bool:
    for m in _QUANT_RE.finditer(text):
        tok = m.group(0).lower()
        if any(u in tok for u in _UNIT) or re.search(r"\d{2,}", tok):
            return True
    return False


# ----------------------------------------------------------------- axes
def keyword_coverage(resume_text: str, ks: KeywordSet | None,
                     job: JobPosting) -> tuple[float, list[str]]:
    rt = _norm(resume_text)
    rtokens = set(rt.split())
    terms: list[tuple[str, float, str]] = []
    if ks and ks.keywords:
        terms = [(k.term, k.weight, k.kind) for k in ks.keywords]
    else:  # fallback: JD required (hard) + preferred (soft)
        terms = [(q, 1.0, "hard") for q in job.required_quals] + \
                [(q, 1.0, "soft") for q in job.preferred_quals]
    if not terms:
        return 0.0, []

    def present(term: str) -> bool:
        n = _norm(term)
        if not n:
            return False
        if n in rt:
            return True
        toks = n.split()
        return bool(toks) and all(t in rtokens for t in toks)

    tot = miss = 0.0
    missing: list[tuple[str, float]] = []
    for term, w, kind in terms:
        weight = w if kind == "hard" else w * 0.5
        tot += weight
        if not present(term):
            miss += weight
            if kind == "hard":
                missing.append((term, weight))
    cov = 100.0 * (tot - miss) / tot if tot else 0.0
    top_missing = [t for t, _ in sorted(missing, key=lambda x: -x[1])][:12]
    return round(cov, 1), top_missing


def quantification(content: ResumeContent) -> tuple[float, float]:
    bl = _bullets(content)
    if not bl:
        return 0.0, 0.0
    frac = sum(_has_metric(b) for b in bl) / len(bl)
    if 0.45 <= frac <= 0.70:               # ideal band
        score = 100.0
    elif frac < 0.45:
        score = frac / 0.45 * 100.0
    else:                                   # over-quantified -> down to 60 at 100%
        score = 100.0 - (frac - 0.70) / 0.30 * 40.0
    return round(max(0.0, min(100.0, score)), 1), round(frac, 2)


def structure(content: ResumeContent, resume_text: str) -> tuple[float, dict]:
    p = prof.load_profile()
    contact = p.get("contact", {})
    checks = {
        "has_summary": bool(content.summary), "wt_has_summary": 15,
        "has_skills": bool(content.skills), "wt_has_skills": 20,
        "has_experience": bool(content.experiences), "wt_has_experience": 25,
        "has_education": bool(content.education or p.get("education")), "wt_has_education": 15,
        "has_email": bool(contact.get("email")), "wt_has_email": 5,
        "has_location": bool(contact.get("location")), "wt_has_location": 5,
        "dates_month_year": bool(_MONYEAR.search(
            " ".join(e.get("dates", "") for e in content.experiences))), "wt_dates_month_year": 15,
    }
    score = sum(checks[f"wt_{k}"] for k in
                ("has_summary", "has_skills", "has_experience", "has_education",
                 "has_email", "has_location", "dates_month_year") if checks[k])
    failed = [k for k in ("has_summary", "has_skills", "has_experience", "has_education",
                          "has_email", "has_location", "dates_month_year") if not checks[k]]
    return float(score), {"failed": failed}


# ----------------------------------------------------------------- main
def score_ats(job: JobPosting, content: ResumeContent, *,
              keyword_set: KeywordSet | None = None,
              semantic_method: str = "lexical") -> ATSScore:
    rt = _resume_text(content)
    kw, missing = keyword_coverage(rt, keyword_set, job)
    quant, quant_frac = quantification(content)
    struct, struct_detail = structure(content, rt)

    reqs = list(job.required_quals) + list(job.responsibilities)
    sem_cov, per = sem.requirement_coverage(reqs, _bullets(content), method=semantic_method)
    weak = sem.weak_of(per, method=semantic_method)

    overall = round(0.5 * kw + 0.3 * quant + 0.2 * struct, 1)
    band = "good" if overall >= 75 else "fair" if overall >= 60 else "weak"
    return ATSScore(
        keyword_coverage=kw, quantification=quant, structure=struct,
        semantic_coverage=round(sem_cov, 1), overall_0_100=overall, band=band,
        semantic_method=semantic_method, missing_keywords=missing,
        weak_requirements=weak[:8],
        detail={"quantified_fraction": quant_frac, "structure": struct_detail,
                "requirements_scored": len(reqs)})
