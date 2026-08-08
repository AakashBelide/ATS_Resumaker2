"""Task 1.5 - deterministic US sponsorship-likelihood scorer.

Backed by the **USCIS H-1B Employer Data Hub** (petition *outcomes*: approvals /
denials aggregated per employer per fiscal year). Direct file URLs download fine
with a browser User-Agent even though the .gov HTML pages 403 bots (blueprint §14).

NO LLM calls - pure data engineering, costs $0.

What this signal is / isn't (be honest in evidence):
  - `lca_count_3y` here is actually USCIS **H-1B petition approvals** (initial +
    continuing) over the trailing 3 available FYs - NOT DOL LCA filings. The
    schema field is named `lca_count_3y` for pipeline compatibility; evidence
    strings label the number accurately.
  - USCIS exposes only the last-4 of the EIN, so we CANNOT join to DOL on tax ID;
    employer-name normalization + fuzzy match is the only bridge (blueprint §14).

TODO (follow-up): add DOL OFLC LCA (ETA-9035) ingest for SOC/title/wage-level
detail so we can score *this role* is sponsorable, not just *this company sponsors*.
The OFLC quarterly .xlsx files are ~1GB, deliberately skipped in this POC.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests as cffi_requests
from rapidfuzz import fuzz, process

from core.schemas import SponsorSignal

# The USCIS .gov CDN (Akamai) 403s bots by TLS/JA3 fingerprint, not just
# User-Agent - plain httpx/requests get 403 even with browser headers. curl_cffi
# impersonates Chrome's TLS handshake, which the direct .csv URLs accept fine
# (blueprint §14 "HTML 403 but files download fine").
_IMPERSONATE = "chrome"

# Cache dir is gitignored (data/ is in .gitignore) - never committed.
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "sponsorship"

_URL = ("https://www.uscis.gov/sites/default/files/document/data/"
        "h1b_datahubexport-{year}.csv")

# How many trailing fiscal years to aggregate.
N_FY = 3


# --------------------------------------------------------------- name normalize
# Legal suffixes / entity types folded away so "Google LLC" == "GOOGLE INC." == "Google".
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "l.l.c", "llp", "lllp", "ltd", "limited",
    "corp", "corporation", "co", "company", "lp", "l.p", "plc", "pllc", "pc",
    "gmbh", "sa", "ag", "nv", "bv", "pvt", "pte", "srl", "spa", "kg", "oy",
    "the", "usa", "us", "na", "n.a", "holdings", "holding", "group", "intl",
    "international", "worldwide", "global", "technologies", "technology",
    "solutions", "services", "systems", "software", "labs", "enterprises",
}
_DBA_RE = re.compile(r"\b(d/?b/?a|f/?k/?a|a/?k/?a)\b.*$")  # drop DBA/FKA/AKA tails


def normalize_name(name: str) -> str:
    """Fold case, drop DBA/FKA tails, strip legal suffixes, punctuation, and
    collapse whitespace so entity variants collapse to one comparable key."""
    if not name:
        return ""
    s = name.lower().strip()
    s = _DBA_RE.sub("", s)                      # "acme dba foo" -> "acme "
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)          # strip punctuation
    # drop legal suffixes AND stray single-letter tokens (e.g. "joe's" -> "joe s";
    # the bare "s" is noise that caused spurious prefix matches).
    tokens = [t for t in s.split()
              if t and t not in _LEGAL_SUFFIXES and (len(t) > 1 or t.isdigit())]
    if not tokens:                              # was ALL suffix words - keep raw
        tokens = [t for t in re.sub(r"[^a-z0-9\s]", " ", s).split() if t]
    return " ".join(tokens)


# --------------------------------------------------------------- ingest
@dataclass
class _EmployerRow:
    employer: str = ""
    initial_approval: int = 0
    initial_denial: int = 0
    continuing_approval: int = 0
    continuing_denial: int = 0
    state: str = ""
    city: str = ""

    @property
    def approvals(self) -> int:
        return self.initial_approval + self.continuing_approval

    @property
    def denials(self) -> int:
        return self.initial_denial + self.continuing_denial


@dataclass
class SponsorIndex:
    """In-memory index over the last N_FY of USCIS data.

    `by_norm[normalized_name]` -> per-FY aggregated rows. Built once, reused for
    many company queries (fuzzy match is over the normalized-name keys)."""
    fiscal_years: list[int] = field(default_factory=list)
    # normalized_name -> {fy: _EmployerRow (summed), ...}
    by_norm: dict[str, dict[int, _EmployerRow]] = field(default_factory=dict)
    # normalized_name -> a representative raw employer name (longest seen)
    display: dict[str, str] = field(default_factory=dict)

    @property
    def norm_keys(self) -> list[str]:
        return list(self.by_norm.keys())


def _to_int(v: str) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def discover_years(max_year: int | None = None, back: int = 12) -> list[int]:
    """Probe USCIS for which FY files exist (HEAD request). Returns available
    years ascending. The .gov HTML 403s bots but the .csv URLs resolve fine."""
    if max_year is None:
        max_year = datetime.now(timezone.utc).year
    found: list[int] = []
    for year in range(max_year, max_year - back, -1):
        try:
            r = cffi_requests.head(_URL.format(year=year),
                                   impersonate=_IMPERSONATE, timeout=30)
            if r.status_code == 200:
                found.append(year)
        except Exception:  # noqa: BLE001 - network hiccup, skip year
            continue
    return sorted(found)


def _cached_csv(year: int) -> Path:
    """Download the USCIS FY csv to the gitignored cache if not already there."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"h1b_datahubexport-{year}.csv"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    url = _URL.format(year=year)
    r = cffi_requests.get(url, impersonate=_IMPERSONATE, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"USCIS FY{year} download failed: HTTP {r.status_code}")
    dest.write_bytes(r.content)
    return dest


def _norm_header(h: str) -> str:
    return h.strip().strip('"').lower().replace(" ", "_")


def build_index(years: list[int] | None = None) -> SponsorIndex:
    """Download (cached) + parse the trailing N_FY USCIS files into an index."""
    if years is None:
        years = discover_years()[-N_FY:]
    idx = SponsorIndex(fiscal_years=sorted(years))
    for year in idx.fiscal_years:
        path = _cached_csv(year)
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = [_norm_header(h) for h in next(reader)]
            col = {name: header.index(name) for name in header}

            def g(row: list[str], key: str) -> str:
                i = col.get(key)
                return row[i] if i is not None and i < len(row) else ""

            for row in reader:
                emp = g(row, "employer").strip()
                if not emp:
                    continue
                norm = normalize_name(emp)
                if not norm:
                    continue
                bucket = idx.by_norm.setdefault(norm, {})
                agg = bucket.setdefault(year, _EmployerRow(employer=emp))
                agg.initial_approval += _to_int(g(row, "initial_approval"))
                agg.initial_denial += _to_int(g(row, "initial_denial"))
                agg.continuing_approval += _to_int(g(row, "continuing_approval"))
                agg.continuing_denial += _to_int(g(row, "continuing_denial"))
                agg.state = agg.state or g(row, "state")
                agg.city = agg.city or g(row, "city")
                # keep the longest raw name as display
                prev = idx.display.get(norm, "")
                if len(emp) > len(prev):
                    idx.display[norm] = emp
    return idx


# --------------------------------------------------------------- matching
# Fuzzy-match threshold on the normalized names (0-100). Below this we treat the
# company as not found in the index.
_MATCH_THRESHOLD = 88
_FUZZY_THRESHOLD = 92   # stricter bar for the typo fallback (avoid spurious matches)


@dataclass
class Match:
    keys: list[str] = field(default_factory=list)  # entity family to aggregate
    score: float = 0.0                              # match confidence 0-100
    anchor: str = ""                                # highest-volume family member
    confidence: str = "high"                        # high | low  (name-match certainty)


def _family_volume(idx: SponsorIndex, key: str) -> int:
    return sum(r.approvals for r in idx.by_norm[key].values())


def match_employer(company: str, idx: SponsorIndex) -> Match:
    """Resolve a query company to the family of USCIS employer entities to
    aggregate, with a confidence tier to avoid false positives.

    Big employers file under many legal entities ("AMAZON.COM SERVICES LLC",
    "AMAZON WEB SERVICES INC", ...), so a company-level signal sums the family.

    Confidence:
      - **high**: an EXACT normalized key equals the query (after suffix
        stripping) -> we trust it and aggregate the query's prefix family.
        (Most real brands collapse to an exact key: "Stripe Payments Inc" ->
        "stripe"; "X Corp" -> "x".)
      - **low**: no exact key, only longer entities START WITH the query token(s)
        -> ambiguous ("linear" -> "linear financial"? "ramp" -> "ramp business"?).
        We keep the best candidate but flag it needs_verification and never let
        it score "high".
      - **unknown** (empty Match): degenerate/too-short query, or fuzzy below bar.

    Guards: a single token of length <=2 ("x") is too ambiguous -> unknown."""
    norm_q = normalize_name(company)
    if not norm_q:
        return Match()
    q_tokens = norm_q.split()
    n = len(q_tokens)
    if n == 1 and len(q_tokens[0]) <= 2:            # e.g. "x" -> too ambiguous
        return Match(confidence="low")

    keyset = set(idx.norm_keys)
    prefix_family = [k for k in idx.norm_keys if k.split()[:n] == q_tokens]

    # HIGH confidence: an exact normalized key exists.
    if norm_q in keyset:
        anchor = max(prefix_family, key=lambda k: _family_volume(idx, k))
        return Match(keys=prefix_family, score=100.0, anchor=anchor, confidence="high")

    # LOW confidence: only longer entities start with the query -> ambiguous.
    if prefix_family:
        # Guard against a short/common token pulling in a large unrelated family:
        # only aggregate members that are the query + at most one extra token
        # (e.g. "ramp business", not the entire "x *" universe).
        narrow = [k for k in prefix_family if len(k.split()) <= n + 1]
        fam = narrow or prefix_family
        anchor = max(fam, key=lambda k: _family_volume(idx, k))
        return Match(keys=fam, score=70.0, anchor=anchor, confidence="low")

    # Typo fallback: strict fuzzy, low confidence, must clear a higher bar.
    best = process.extractOne(norm_q, idx.norm_keys, scorer=fuzz.token_set_ratio)
    if best is None:
        return Match()
    key, score, _ = best
    if score < _FUZZY_THRESHOLD:
        return Match(score=float(score), confidence="low")
    return Match(keys=[key], score=float(score), anchor=key, confidence="low")


# --------------------------------------------------------------- scoring
# Likelihood thresholds (documented, deterministic):
#   high   : >= 100 approvals over 3 FY AND filed in the most recent FY AND
#            approval_rate >= 0.80
#   medium : >= 10 approvals over 3 FY AND approval_rate >= 0.50
#            (recency not required - lower but real sponsorship history)
#   low    : any approvals recorded but below the medium bar
#   unknown: employer not found in the USCIS index at all
_HIGH_VOLUME = 100
_HIGH_RATE = 0.80
_MED_VOLUME = 10
_MED_RATE = 0.50


def _likelihood(count_3y: int, filed_recent: bool, rate: float | None) -> str:
    if count_3y == 0:
        return "unknown"
    r = rate if rate is not None else 0.0
    if count_3y >= _HIGH_VOLUME and filed_recent and r >= _HIGH_RATE:
        return "high"
    if count_3y >= _MED_VOLUME and r >= _MED_RATE:
        return "medium"
    return "low"


def score_company(company: str, idx: SponsorIndex) -> SponsorSignal:
    """Score one company into a SponsorSignal off the prebuilt index."""
    match = match_employer(company, idx)
    if not match.keys:
        return SponsorSignal(
            company=company,
            normalized_name=normalize_name(company),
            likelihood="unknown",
            evidence=[
                "No matching employer found in USCIS H-1B Employer Data Hub "
                f"for FY{'-'.join(str(y) for y in idx.fiscal_years)} "
                f"(best fuzzy score {match.score:.0f} < {_FUZZY_THRESHOLD}).",
                "Absence is not proof a company never sponsors - small/new "
                "sponsors and pure-PERM (green-card) sponsors may not appear "
                "in H-1B petition data.",
            ],
        )

    # Aggregate the entity family per fiscal year.
    per_fy: dict[int, _EmployerRow] = {}
    for key in match.keys:
        for fy, r in idx.by_norm[key].items():
            agg = per_fy.setdefault(fy, _EmployerRow())
            agg.initial_approval += r.initial_approval
            agg.initial_denial += r.initial_denial
            agg.continuing_approval += r.continuing_approval
            agg.continuing_denial += r.continuing_denial

    approvals = sum(r.approvals for r in per_fy.values())
    denials = sum(r.denials for r in per_fy.values())
    total = approvals + denials
    rate = (approvals / total) if total else None
    recent_fy = max(idx.fiscal_years)
    filed_recent = recent_fy in per_fy and per_fy[recent_fy].approvals > 0
    most_recent_with_data = max(
        (fy for fy, r in per_fy.items() if r.approvals > 0), default=recent_fy)

    likelihood = _likelihood(approvals, filed_recent, rate)
    anchor_key = match.anchor or match.keys[0]
    display = idx.display.get(anchor_key, company)

    # Low-confidence (prefix/fuzzy, no exact key): the entity might not be the
    # company the user means -> never claim "high", and flag for verification.
    low_conf = match.confidence != "high"
    if low_conf and likelihood == "high":
        likelihood = "medium"

    fy_bits = ", ".join(
        f"FY{fy}: {per_fy[fy].approvals} approvals/{per_fy[fy].denials} denials"
        for fy in sorted(per_fy)
    )
    n_ent = len(match.keys)
    if n_ent == 1:
        match_line = (f"Matched USCIS employer '{display}' "
                      f"(normalized '{anchor_key}', match {match.score:.0f}/100).")
    else:
        top = sorted(match.keys, key=lambda k: _family_volume(idx, k),
                     reverse=True)[:3]
        top_str = "; ".join(f"{idx.display.get(k, k)} ({_family_volume(idx, k):,})"
                            for k in top)
        match_line = (f"Aggregated {n_ent} related USCIS entities under the "
                      f"'{anchor_key}' name family (top by volume: {top_str}).")

    evidence = [
        match_line,
        f"USCIS H-1B petition APPROVALS (initial+continuing) over "
        f"FY{min(idx.fiscal_years)}-FY{max(idx.fiscal_years)}: "
        f"{approvals:,} (this is petition-outcome data, NOT DOL LCA filings).",
        f"Per fiscal year -> {fy_bits}.",
        (f"Approval rate: {rate:.1%} ({approvals:,} approvals / "
         f"{total:,} decisions)." if rate is not None
         else "Approval rate: n/a (no decisions recorded)."),
        (f"Filed in the most recent available FY ({recent_fy}) -> active sponsor."
         if filed_recent
         else f"No approvals in the most recent available FY ({recent_fy}); "
              f"last activity FY{most_recent_with_data}."),
        f"Likelihood '{likelihood}' from thresholds: high needs "
        f">={_HIGH_VOLUME} approvals + recent-FY activity + "
        f">={_HIGH_RATE:.0%} approval rate; medium needs >={_MED_VOLUME} "
        f"approvals + >={_MED_RATE:.0%} rate.",
    ]

    if low_conf:
        evidence.insert(0, (
            f"[LOW-CONFIDENCE MATCH] No exact USCIS entity named '{normalize_name(company)}'; "
            f"matched '{display}' by prefix/fuzzy ({match.score:.0f}/100). "
            "VERIFY this is the same company before relying on it (could be a "
            "different firm with a similar name)."))

    return SponsorSignal(
        company=company,
        normalized_name=anchor_key,
        lca_count_3y=approvals,  # petition approvals; named for schema compat
        most_recent_fy=str(most_recent_with_data),
        approval_rate=round(rate, 4) if rate is not None else None,
        likelihood=likelihood,
        confidence="high" if not low_conf else "low",
        needs_verification=low_conf,
        evidence=evidence,
    )


# --------------------------------------------------------------- convenience
_INDEX_CACHE: SponsorIndex | None = None


def get_index() -> SponsorIndex:
    """Process-level singleton so repeated scores reuse one parsed index."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = build_index()
    return _INDEX_CACHE


def sponsor_signal(company: str) -> SponsorSignal:
    """One-shot: build/reuse the index and score a single company."""
    return score_company(company, get_index())
