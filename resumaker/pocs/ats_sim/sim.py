"""Local ATS + recruiter simulation (Phase 3).

Answers the owner's "does my resume actually pop up?" test without the heavy
OpenCATS infra, and reproducibly ($0, no LLM):

  1. PARSE FIDELITY  - extract the fields a real ATS (Textkernel-style) captures
     from the resume text: name, contact, location, links, sections, experience
     entries (org/title/dates), skills, education. A resume that doesn't parse
     into fields never surfaces.
  2. RECRUITER SEARCH - Boolean surfacing: does the resume contain the JD's
     must-have query terms (so it appears in the recruiter's filtered search)?
  3. RANKING          - BM25 relevance of the resume vs a pool of decoy resumes
     for the JD query: does ours rank #1 / above the decoys?

(OpenCATS remains an optional manual "full recruiter UI" check; this harness is
the automated, CI-able core.)
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# --------------------------------------------------------------- parse fidelity
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
# same-line City + 2-letter state (do NOT let \s cross newlines and swallow the name)
_CITY = re.compile(r"\b([A-Z][A-Za-z.'-]+(?:[ \t][A-Z][A-Za-z.'-]+){0,3}),[ \t]*([A-Z]{2})\b")
_SECTIONS = ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"]
_HEADER = re.compile(r"^(.+?)\s+-\s+(.+?)\s*(?:\|\s*(.+?))?\s{2,}([A-Za-z].*\d{4}.*)$")
_MONYEAR = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}", re.I)


@dataclass
class ParseCard:
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    completeness: float = 0.0
    missing: list[str] = field(default_factory=list)


def parse_resume(text: str) -> ParseCard:
    """Deterministic field extraction, mimicking an ATS parser on plain text."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    nonblank = [ln for ln in lines if ln.strip()]
    card = ParseCard()

    card.name = nonblank[0].strip() if nonblank else ""
    if m := _EMAIL.search(text):
        card.email = m.group(0)
    if m := _PHONE.search(text):
        card.phone = m.group(0).strip()
    if m := _CITY.search(text):
        card.location = f"{m.group(1)}, {m.group(2)}"
    for lbl in ("Portfolio", "LinkedIn", "GitHub"):
        if re.search(rf"\b{lbl}\b", text):
            card.links.append(lbl)

    up = text.upper()
    card.sections = [s for s in _SECTIONS if s in up]

    # experience entries: "Company - Title | Location <tab/spaces> Month YYYY - ..."
    for ln in lines:
        if m := _HEADER.match(ln.strip()):
            org, title, loc, dates = m.groups()
            if _MONYEAR.search(dates) or re.search(r"\b\d{4}\b", dates):
                card.experience.append({"organization": org.strip(),
                                        "title": title.strip(),
                                        "dates": dates.strip()})

    # skills: lines that look like "Category: a | b | c" under the SKILLS section
    in_skills = False
    for ln in lines:
        u = ln.strip().upper()
        if u in _SECTIONS:
            in_skills = (u == "SKILLS")
            continue
        if in_skills and "|" in ln:
            after = ln.split(":", 1)[1] if ":" in ln else ln
            card.skills += [s.strip() for s in after.split("|") if s.strip()]

    card.education = [ln.strip() for ln in lines
                      if re.search(r"\b(B\.?Tech|Bachelor|Master|M\.?S\.?|B\.?S\.?|PhD|University|Institute)\b", ln)]

    expected = {"name": card.name, "email": card.email, "phone": card.phone,
                "location": card.location, "links": card.links,
                "experience": card.experience, "skills": card.skills,
                "education": card.education,
                "all_sections": len(card.sections) >= 4}
    got = [k for k, v in expected.items() if v]
    card.missing = [k for k, v in expected.items() if not v]
    card.completeness = round(100.0 * len(got) / len(expected), 1)
    return card


# --------------------------------------------------------------- recruiter search + BM25
def _tok(t: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", (t or "").lower())


def bm25_scores(query_terms: list[str], docs: list[str], k1: float = 1.5,
                b: float = 0.75) -> list[float]:
    dtoks = [_tok(d) for d in docs]
    n = len(docs) or 1
    avgdl = (sum(len(d) for d in dtoks) / n) or 1.0
    df: Counter = Counter()
    for dt in dtoks:
        df.update(set(dt))
    qwords = [w for term in query_terms for w in _tok(term)]
    scores = []
    for dt in dtoks:
        tf = Counter(dt)
        dl = len(dt) or 1
        s = 0.0
        for w in qwords:
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * (tf[w] * (k1 + 1)) / (tf[w] + k1 * (1 - b + b * dl / avgdl))
        scores.append(round(s, 3))
    return scores


def boolean_surface(text: str, must_have: list[str]) -> tuple[bool, list[str], list[str]]:
    """Recruiter Boolean filter: does the resume contain the must-have terms?
    Returns (surfaces, present, absent). A term is present if all its tokens appear."""
    toks = set(_tok(text))
    present, absent = [], []
    for term in must_have:
        (present if all(w in toks for w in _tok(term)) else absent).append(term)
    return (len(present) >= max(1, len(must_have) - 1)), present, absent  # allow 1 miss


def rank_pool(query_terms: list[str], pool: list[tuple[str, str]]) -> list[dict]:
    """pool = [(label, text)]. Returns ranked list (desc) with bm25 + rank."""
    scores = bm25_scores(query_terms, [t for _, t in pool])
    rows = [{"label": lbl, "score": sc} for (lbl, _), sc in zip(pool, scores)]
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
