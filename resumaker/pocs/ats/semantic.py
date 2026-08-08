"""Per-requirement semantic coverage (blueprint 11).

For each JD requirement, find the best-matching resume bullet and score similarity,
so we can flag requirements the resume under-evidences - exactly how Eightfold/
Workday-style semantic ATS match (embed + cosine), surfaced as a truthful
"what's weakly covered" list.

Two methods:
  - "lexical" (default): pure-Python TF-IDF cosine. Deterministic, offline, $0.
    A keyword-overlap proxy for semantics (honest about that).
  - "gemini": real embeddings via the Gemini API (google-genai). True semantic
    matching; costs pennies (guarded by cost_guard, well under the $5 cap).
"""
from __future__ import annotations

import math
import re
from collections import Counter

_STOP = set(
    "a an the of to in for and or with on at by from as is are be been was were "
    "this that these those you your we our it its their they them he she his her "
    "will would can could should may might must have has had do does did not no "
    "into over under across per via using use used build built work working across "
    "including etc across strong ability experience years year role team teams".split())

# similarity thresholds below which a requirement counts as "weakly covered".
# lexical = idf-weighted token RECALL (fraction of the requirement's meaningful
# content present in the best-matching bullet); gemini = embedding cosine.
# NOTE: the gemini threshold is a starting default for gemini-embedding-001 and
# should be calibrated on a labeled set; "lexical" is the reproducible ($0) default.
_WEAK = {"lexical": 0.40, "gemini": 0.62}


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-zA-Z0-9+#.]+", (text or "").lower())
    out: list[str] = []
    for t in toks:
        t = t.strip(".")
        if len(t) < 2 or t in _STOP or t.isdigit():
            continue
        out.append(t)
    return out


def _tf(tokens: list[str]) -> dict[str, float]:
    c = Counter(tokens)
    n = len(tokens) or 1
    return {k: v / n for k, v in c.items()}


def build_idf(docs_tokens: list[list[str]]) -> dict[str, float]:
    n = len(docs_tokens) or 1
    df: Counter = Counter()
    for toks in docs_tokens:
        df.update(set(toks))
    return {t: math.log((n + 1) / (df[t] + 1)) + 1.0 for t in df}


def tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    return {t: tf * idf.get(t, 1.0) for t, tf in _tf(tokens).items()}


def cosine(a: dict[str, float] | list[float], b: dict[str, float] | list[float]) -> float:
    if isinstance(a, dict):
        common = set(a) & set(b)
        num = sum(a[t] * b[t] for t in common)
        da = math.sqrt(sum(v * v for v in a.values()))
        db = math.sqrt(sum(v * v for v in b.values()))
    else:
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a))
        db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0


def _gemini_embed(texts: list[str]) -> list[list[float]]:
    """Real embeddings via google-genai, guarded by the Gemini budget."""
    from core.cost_guard import check_gemini, record
    from core.llm import GeminiProvider  # noqa: F401  (ensures env/SDK present)
    from google import genai

    check_gemini(0.001)
    client = genai.Client()
    res = client.models.embed_content(model="gemini-embedding-001", contents=texts)
    vecs = [list(e.values) for e in res.embeddings]
    approx_tok = sum(len(t) for t in texts) // 4
    record("gemini", "gemini-embedding-001", approx_tok, 0, cost_usd=approx_tok / 1e6 * 0.15)
    return vecs


def requirement_coverage(requirements: list[str], bullets: list[str],
                         method: str = "lexical") -> tuple[float, list[tuple[str, float]]]:
    """Return (coverage_pct, per_requirement[(requirement, best_similarity)]).
    coverage_pct = % of requirements whose best-matching bullet clears the method
    threshold (i.e. is genuinely evidenced)."""
    requirements = [r for r in requirements if r and r.strip()]
    bullets = [b for b in bullets if b and b.strip()]
    if not requirements or not bullets:
        return 0.0, [(r, 0.0) for r in requirements]

    if method == "gemini":
        vecs = _gemini_embed(requirements + bullets)
        rvecs, bvecs = vecs[:len(requirements)], vecs[len(requirements):]
        per = [(r, max(cosine(rv, bv) for bv in bvecs))
               for r, rv in zip(requirements, rvecs)]
    else:  # lexical: idf-weighted token recall of the requirement in the best bullet
        idf = build_idf([tokenize(t) for t in requirements + bullets])
        btoksets = [set(tokenize(b)) for b in bullets]
        per = []
        for r in requirements:
            rtoks = set(tokenize(r))
            denom = sum(idf.get(t, 1.0) for t in rtoks) or 1.0
            best = max((sum(idf.get(t, 1.0) for t in (rtoks & bt)) / denom
                        for bt in btoksets), default=0.0)
            per.append((r, best))

    thr = _WEAK.get(method, 0.12)
    covered = sum(1 for _, s in per if s >= thr)
    return 100.0 * covered / len(requirements), per


def weak_of(per: list[tuple[str, float]], method: str = "lexical") -> list[str]:
    thr = _WEAK.get(method, 0.12)
    return [r for r, s in sorted(per, key=lambda x: x[1]) if s < thr]
