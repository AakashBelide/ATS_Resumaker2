"""Gap analysis (Task 1.4).

Classify each JD requirement against the canonical profile as:
  - existing            : a skill/tool the candidate explicitly lists
  - supportedByResume   : demonstrated in their experience/projects prose, not named
  - gap                 : no evidence in the profile

For gaps, if the profile owns a directly equivalent tool (per profile.equivalence_map),
propose an HONEST substitution (owned -> required) so the resume can bridge it
truthfully (blueprint §9) instead of claiming the tool outright.

Anti-hallucination: the LLM must cite profile evidence for existing/supported; we then
VERIFY that evidence actually appears in the profile. Unverifiable claims are downgraded
to `gap` with a warning -- the model cannot invent a match.
"""
from __future__ import annotations

import json
import re

from resumaker.domain import GapItem, GapReport, JobPosting, KeywordSet
from resumaker.persistence import profile as prof
from resumaker.providers.llm import get_provider

SYSTEM = ("You classify job requirements against a candidate's profile. Ground every "
          "judgment ONLY in the provided profile. Never invent evidence. If a "
          "requirement has no support, say gap.")

PROMPT = """CANDIDATE PROFILE (the only source of truth):
{profile}

NAMED SKILLS: {skills}

EQUIVALENCE MAP (owned_tool -> equivalents the candidate can legitimately bridge to):
{equiv}

JOB REQUIREMENTS to classify:
{reqs}

For EACH requirement return an object:
  "requirement": the requirement text
  "status": "existing" | "supportedByResume" | "gap"
     - existing: matches a NAMED SKILL above (allow synonyms/acronyms, e.g. LLMs == large language models, K8s == Kubernetes)
     - supportedByResume: NOT a named skill, but clearly demonstrated in the profile's
       experience/project bullets. Provide the exact snippet as evidence.
     - gap: no evidence anywhere in the profile.

  RECOGNIZE THE SAME CAPABILITY UNDER DIFFERENT WORDING. A requirement is `existing` or
  `supportedByResume` when the underlying technique or outcome is shown, even if the exact term
  differs. Judge by capability, not keywords. For example:
     - "fuzzy matching" / "approximate matching" / "fuzzy search" <- entity resolution, record
       linkage, deduplication, similarity matching, address/name/record matching, dedup engines
     - "entity resolution" / "identity graph" <- deduplication, record linkage, graph of entities
     - "streaming" / "real-time" <- real-time APIs/pipelines, Kafka, event processing
     - "orchestration" <- Airflow, LangGraph, multi-agent routing
     - "graph database" <- Neo4j, TigerGraph, graph-based systems
  Be consistent: if you credit one phrasing of a capability, credit its synonyms too. You MUST still
  cite a verbatim profile snippet as evidence for existing/supportedByResume; if none demonstrates
  the capability, it is a genuine gap.
  "evidence": for existing -> the matching skill name; for supportedByResume -> a short
     verbatim snippet copied from a profile bullet; for gap -> "".
  "substitution": ONLY for a gap that the EQUIVALENCE MAP can bridge -> the owned_tool
     name (which must be a real named skill). Otherwise "".

Return ONLY a JSON array of these objects, one per requirement."""


def _requirements(jd) -> list[str]:
    if isinstance(jd, JobPosting):
        reqs = list(jd.required_quals) + list(jd.preferred_quals)
        return reqs or ([k for k in re.split(r"[\n;]", jd.raw_text) if len(k.strip()) > 8][:15])
    if isinstance(jd, KeywordSet):
        return list(jd.standardized)
    if isinstance(jd, (list, tuple)):
        return list(jd)
    raise TypeError(f"unsupported input: {type(jd)}")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def _verify_evidence(status: str, evidence: str, skills_norm: set[str],
                     bullets_norm: str) -> bool:
    """True if the cited evidence is actually grounded in the profile."""
    ev = _norm(evidence).strip()
    if not ev:
        return False
    if status == "existing":
        # evidence should look like a named skill; allow token-subset match
        ev_tokens = set(ev.split())
        return any(ev_tokens & set(s.split()) and ev_tokens <= set(s.split()) | ev_tokens
                   for s in skills_norm) or any(ev in s or s in ev for s in skills_norm)
    # supportedByResume: a snippet should appear in the bullet corpus
    frag = " ".join(ev.split()[:6])
    return len(frag) >= 6 and frag in bullets_norm


def analyze_gaps(jd, *, provider: str = "claude", model: str = "sonnet") -> GapReport:
    reqs = _requirements(jd)
    if not reqs:
        raise ValueError("no requirements to analyze")

    skills = sorted(prof.all_skills())
    equiv = prof.equivalence_map()
    llm = get_provider(provider, model=model)
    raw = llm.complete_json(
        PROMPT.format(profile=prof.profile_text()[:9000],
                      skills=", ".join(skills),
                      equiv=json.dumps(equiv),
                      reqs="\n".join(f"- {r}" for r in reqs)),
        system=SYSTEM, temperature=0.0, max_tokens=2500, task="gap_analysis")

    skills_norm = {_norm(s) for s in skills}
    bullets_norm = _norm(" ".join(prof.all_bullets()))
    owned_norm = {_norm(k) for k in equiv}

    items: list[GapItem] = []
    gaps: list[str] = []
    subs: list[str] = []
    for obj in raw if isinstance(raw, list) else []:
        if not isinstance(obj, dict):
            continue
        req = str(obj.get("requirement", "")).strip()
        status = str(obj.get("status", "gap")).strip()
        evidence = str(obj.get("evidence", "")).strip()
        substitution = str(obj.get("substitution", "")).strip()
        if not req:
            continue
        if status not in ("existing", "supportedByResume", "gap"):
            status = "gap"

        # Anti-hallucination: verify cited evidence; downgrade if unverifiable.
        if status in ("existing", "supportedByResume"):
            if not _verify_evidence(status, evidence, skills_norm, bullets_norm):
                status, evidence = "gap", ""

        # Validate substitution: owned tool must actually be a named skill.
        if substitution and _norm(substitution) not in owned_norm and \
                _norm(substitution) not in skills_norm:
            substitution = ""

        items.append(GapItem(requirement=req, status=status,
                             evidence=evidence, substitution=substitution))
        if status == "gap":
            if substitution:
                subs.append(f"{substitution} -> {req}")
            else:
                gaps.append(req)

    return GapReport(items=items, gaps=gaps, substitutions=subs)
