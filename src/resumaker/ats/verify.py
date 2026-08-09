"""ATS-parse verification (Task 1.10, blueprint 10 + Appendix B9).

Runs on a generated resume and gates the pipeline. Independent of the fact-gate
(1.9): the fact-gate stops fabrication; THIS stops the resume from being unreadable
to an ATS, embarrassing to a recruiter, or inconsistent with the candidate's record.

Checks (blockers fail the resume; warnings are advisory):
  - Text-extraction round-trip: the rendered PDF extracts cleanly, all sections
    present and in the intended linear order, contact info present (not jumbled).
  - ASCII/Unicode: no non-ASCII glyphs (em-dash etc.) in content that corrupt
    parsing / read as an AI tell (benign PDF list-bullet markers are ignored).
  - Spelling gate: unknown words flagged via pyspellchecker; a token with a
    correction is a high-confidence typo (blocker) - typos are the #1 recruiter red
    flag. Tech terms/proper nouns are allow-listed from the profile.
  - Resume<->record consistency (B9): every resume employer/title/tenure must trace
    to the canonical profile (the LinkedIn-truth proxy). A company not in the profile
    or an INFLATED tenure is a blocker; a reframed title is a warning.
  - Headline exact-title match (1/8): headline should carry the JD title.
  - Vary-structure (2): ~40-70% of bullets quantified; outside -> warning.
"""
from __future__ import annotations

import re
from functools import lru_cache

from resumaker.ats.scorer import _bullets, _has_metric
from resumaker.domain import JobPosting, ResumeContent, VerifyReport
from resumaker.persistence import profile as prof

_SECTIONS = ["SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"]
_MONYEAR = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(19|20)\d{2}", re.I)
_YEAR = re.compile(r"(19|20)\d{2}")

# Benign non-ASCII codepoints in an extracted PDF (list-bullet markers, nbsp,
# zero-width, BOM): layout decoration, not content corruption -> ignore in the scan.
_BENIGN = {0xF0B7, 0xF0A7, 0xF076, 0x2022, 0x25CF, 0x25AA, 0x2023, 0x25E6,
           0x2043, 0x00A0, 0x200B, 0xFEFF}


# --------------------------------------------------------------- spelling
@lru_cache(maxsize=1)
def _allowlist() -> set[str]:
    """Domain terms that are correct even if not in the dictionary: everything the
    candidate really writes (skills/employers/titles/bullets) + common tech terms."""
    p = prof.load_profile()
    toks: set[str] = set()
    for blob in (prof.profile_text(), " ".join(prof.all_skills()),
                 " ".join(prof.all_employers()), " ".join(prof.all_titles()),
                 p.get("contact", {}).get("name", "")):
        toks |= {t.lower() for t in re.findall(r"[A-Za-z]+", blob)}
    toks |= {
        # acronyms / product names
        "ai", "ml", "genai", "llm", "llms", "rag", "mlops", "llmops", "nl2sql",
        "api", "apis", "aws", "gcp", "sql", "nosql", "etl", "elt", "ci", "cd",
        "kubernetes", "docker", "terraform", "airflow", "snowflake", "bigquery",
        "pyspark", "langgraph", "langchain", "crewai", "qdrant", "neo4j", "fastapi",
        "opentelemetry", "openai", "gpt", "vlm", "ocr", "roi", "sdk", "cli", "gpu",
        "cpu", "grpc", "graphql", "oauth", "sso", "yaml", "json", "csv", "http",
        "https", "ui", "ux", "kpi", "kpis", "adx", "aks", "vm", "vms",
        # common tech words the base dictionary lacks / mis-corrects
        "async", "await", "auth", "backend", "frontend", "fullstack", "middleware",
        "runtime", "realtime", "dataset", "datasets", "dataframe", "dataframes",
        "changelog", "timestamp", "config", "namespace", "tokenizer", "tokenization",
        "embeddings", "embedding", "chatbot", "chatbots", "scalable", "observability",
        "agentic", "vectordb", "devops", "webhook", "webhooks", "serverless",
        "microservice", "microservices", "dedup", "deduplicate", "deduplicating",
        "deduplication", "orchestrator", "orchestration", "multimodal", "multitenant",
        "throughput", "latency", "workflow", "workflows", "upsell",
        "knowledgebase", "onboarding", "roadmap", "stakeholder", "stakeholders"}
    return toks


@lru_cache(maxsize=1)
def _speller():
    from spellchecker import SpellChecker
    sp = SpellChecker(distance=1)                # includes inflected forms; fast
    sp.word_frequency.load_words(_allowlist())   # never flag domain terms
    return sp


def _stem_variants(w: str) -> set[str]:
    """Inflectional stems of w (plural/past/gerund) to avoid flagging valid
    inflections of known words (e.g. 'workflows' -> 'workflow')."""
    v: set[str] = set()
    for suf in ("s", "es", "ed", "ing", "d"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            v.add(w[: -len(suf)])
    if w.endswith("ies"):
        v.add(w[:-3] + "y")
    return v


def _spelling(text: str) -> tuple[list[str], list[str]]:
    sp = _speller()
    allow = _allowlist()
    typos: list[str] = []
    suspects: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z']+", text):
        # skip camelCase / ALLCAPS / anything with digits (tech names, acronyms)
        if any(ch.isdigit() for ch in raw):
            continue
        if raw != raw.lower() and raw != raw.capitalize():
            continue
        w = raw.lower().strip("'")
        if len(w) < 4 or w in seen:
            continue
        seen.add(w)
        if w in sp:
            continue
        # a valid inflection of a known/allow-listed word is not a typo
        if any(s in sp or s in allow for s in _stem_variants(w)):
            continue
        corr = sp.correction(w)
        (typos if corr and corr != w else suspects).append(w)
    return typos, suspects


# --------------------------------------------------------------- consistency (B9)
def _year_range(dates: str) -> tuple[int, int]:
    yrs = [int(m.group(0)) for m in _YEAR.finditer(dates or "")]
    end = 9999 if re.search(r"present|current|now", (dates or ""), re.I) else (max(yrs) if yrs else 0)
    return (min(yrs) if yrs else 0, end)


def _profile_org_spans() -> dict[str, tuple[int, int, set[str]]]:
    """org(lower) -> (earliest_start_year, latest_end_year, {titles})."""
    spans: dict[str, tuple[int, int, set[str]]] = {}
    for e in prof.load_profile().get("experience", []):
        org = e.get("organization", "").strip().lower()
        if not org:
            continue
        s, en = _year_range(f"{e.get('start_date','')} - {e.get('end_date','')}")
        cur = spans.get(org, (9999, 0, set()))
        spans[org] = (min(cur[0], s or 9999), max(cur[1], en),
                      cur[2] | ({e.get("title", "").strip().lower()} if e.get("title") else set()))
    return spans


def _consistency(content: ResumeContent) -> tuple[list[str], list[str]]:
    spans = _profile_org_spans()
    blockers: list[str] = []
    warnings: list[str] = []
    for e in content.experiences:
        org = e.get("organization", "").strip().lower()
        title = e.get("title", "").strip()
        match = next((k for k in spans if k == org or k in org or org in k), None)
        if not match:
            blockers.append(f"Experience '{e.get('organization')}' is not in the profile "
                            f"(resume<->record inconsistency).")
            continue
        pstart, pend, ptitles = spans[match]
        rs, re_ = _year_range(e.get("dates", ""))
        if rs and rs < pstart:
            blockers.append(f"{e.get('organization')}: resume start {rs} precedes profile "
                            f"start {pstart} (inflated tenure).")
        if re_ != 9999 and pend != 9999 and re_ > pend:
            blockers.append(f"{e.get('organization')}: resume end {re_} exceeds profile "
                            f"end {pend} (inflated tenure).")
        tl = title.lower()
        if title and not any(tl == pt or tl in pt or pt in tl for pt in ptitles):
            warnings.append(f"{e.get('organization')}: title '{title}' is a reframe not "
                            f"directly in the profile - confirm it matches LinkedIn.")
    return blockers, warnings


# --------------------------------------------------------------- structure / order
def _nonascii_bad(text: str) -> list[str]:
    return sorted({c for c in text if ord(c) > 127 and ord(c) not in _BENIGN})


def _round_trip(pdf_path: str) -> tuple[list[str], list[str], dict]:
    from resumaker.stages.resume.render_pdf import extract_text
    text = extract_text(pdf_path)
    up = text.upper()
    present = [s for s in _SECTIONS if s in up]
    positions = [up.find(s) for s in present]
    ordered = positions == sorted(positions)
    blockers: list[str] = []
    for must in ("EXPERIENCE", "SKILLS", "EDUCATION"):
        if must not in present:
            blockers.append(f"Section '{must}' missing from extracted PDF text (parse failure).")
    if not ordered:
        blockers.append("Sections extract out of order (jumbled parse) - ATS will misread.")
    contact = prof.load_profile().get("contact", {})
    if contact.get("email") and contact["email"] not in text:
        blockers.append("Contact email not found in extracted text (in header/footer or corrupted).")
    bad = _nonascii_bad(text)
    if bad:
        blockers.append(f"Non-ASCII characters in extracted text: {bad[:8]} "
                        f"(corrupts parsing / AI tell).")
    return blockers, [], {"sections_present": present, "linear_order_ok": ordered,
                          "chars_extracted": len(text)}


def _content_text(content: ResumeContent) -> str:
    parts = [content.headline, content.summary, *_bullets(content)]
    for cat, items in (content.skills or {}).items():
        parts += [cat, *items]
    return "\n".join(p for p in parts if p)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# --------------------------------------------------------------- main
def verify_ats(job: JobPosting, content: ResumeContent, *,
               pdf_path: str | None = None) -> VerifyReport:
    blockers: list[str] = []
    warnings: list[str] = []
    checks: dict = {}

    # 1) round-trip (needs the rendered PDF) or section presence from content
    if pdf_path:
        b, w, rt = _round_trip(pdf_path)
        blockers += b; warnings += w; checks["round_trip"] = rt
    else:
        for must in ("experiences", "skills"):
            if not getattr(content, must):
                blockers.append(f"Resume content missing '{must}'.")

    text = _content_text(content)

    # 2) ASCII on content (em-dashes/smart quotes/arrows must be normalized away)
    bad = _nonascii_bad(text)
    if bad:
        blockers.append(f"Non-ASCII characters in content: {bad[:8]}.")
    checks["ascii_clean"] = not bad

    # 3) spelling
    typos, suspects = _spelling(text)
    if typos:
        blockers.append(f"Likely misspellings: {typos[:8]}.")
    if suspects:
        warnings.append(f"Unrecognized words to review (may be fine): {suspects[:10]}.")
    checks["spelling"] = {"typos": typos, "suspects": suspects[:15]}

    # 4) resume<->record consistency (B9)
    cb, cw = _consistency(content)
    blockers += cb; warnings += cw

    # 5) headline exact-title match
    has_title = bool(job.title) and _norm(job.title) in _norm(content.headline)
    if job.title and not has_title:
        warnings.append(f"Headline '{content.headline}' does not contain the JD title "
                        f"'{job.title}' - title match is the #1 search/scan factor.")
    checks["headline_has_jd_title"] = has_title

    # 6) dates Month YYYY
    if content.experiences and not _MONYEAR.search(
            " ".join(e.get("dates", "") for e in content.experiences)):
        warnings.append("Experience dates are not in 'Month YYYY' format (can cause false gaps).")

    # 7) vary-structure (~40-70% quantified)
    bl = _bullets(content)
    frac = sum(_has_metric(b) for b in bl) / len(bl) if bl else 0.0
    checks["quantified_fraction"] = round(frac, 2)
    if frac > 0.75:
        warnings.append(f"{int(frac*100)}% of bullets are quantified - over the ~50-60% "
                        f"target; metric-in-every-bullet reads formulaic/AI-generated.")
    elif frac < 0.4:
        warnings.append(f"Only {int(frac*100)}% of bullets are quantified - add measurable impact.")

    return VerifyReport(passed=not blockers, blockers=blockers,
                        warnings=warnings, checks=checks)
