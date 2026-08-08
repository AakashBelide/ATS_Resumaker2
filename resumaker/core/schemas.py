"""Shared I/O contracts across all POCs. Every pipeline stage produces/consumes
one of these Pydantic models, so components stay swappable and testable.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- Job posting
class WorkModel(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    unknown = "unknown"


class Knockout(BaseModel):
    question: str
    kind: Literal["work_auth", "sponsorship", "years_experience", "location",
                  "relocation", "salary", "notice", "education", "license",
                  "clearance", "other"] = "other"
    hard: bool = True  # disqualifying if failed


class JobPosting(BaseModel):
    """Structured JD (Task 1.2 output)."""
    title: str = ""
    company: str = ""
    location: str = ""
    work_model: WorkModel = WorkModel.unknown
    remote_restriction: str = ""          # e.g. "US only", "ET timezone"
    seniority: str = ""                   # intern/new-grad/mid/senior/staff/...
    required_quals: list[str] = Field(default_factory=list)
    preferred_quals: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    salary_range: str = ""
    work_auth_note: str = ""              # verbatim work-auth/sponsorship text if stated
    # Structured sponsorship stance parsed from the JD itself (the most
    # authoritative, role-specific signal; overrides USCIS history in 1.7):
    #   offers        -> JD says it sponsors / is open to sponsorship
    #   no_sponsorship-> JD says no sponsorship / must be authorized w/o sponsorship
    #   case_by_case  -> conditional / "may consider"
    #   unclear       -> JD is silent on sponsorship
    sponsorship_stance: Literal["offers", "no_sponsorship",
                                "case_by_case", "unclear"] = "unclear"
    knockouts: list[Knockout] = Field(default_factory=list)
    raw_text: str = ""
    source_url: str = ""
    source_type: str = ""                 # greenhouse|lever|ashby|playwright|...


# ---------------------------------------------------------------- Keywords
class WeightedKeyword(BaseModel):
    term: str
    weight: float = 1.0
    kind: Literal["hard", "soft"] = "hard"


class KeywordSet(BaseModel):
    """Task 1.3 output. `standardized` is the frozen set reused for scoring."""
    keywords: list[WeightedKeyword] = Field(default_factory=list)
    standardized: list[str] = Field(default_factory=list)

    @property
    def hard(self) -> list[str]:
        return [k.term for k in self.keywords if k.kind == "hard"]

    @property
    def soft(self) -> list[str]:
        return [k.term for k in self.keywords if k.kind == "soft"]


# ---------------------------------------------------------------- Gap analysis
class GapItem(BaseModel):
    requirement: str
    status: Literal["existing", "supportedByResume", "gap"]
    evidence: str = ""                    # profile bullet/skill backing it
    substitution: str = ""                # equivalence-map bridge, if any


class GapReport(BaseModel):
    """Task 1.4 output."""
    items: list[GapItem] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)          # true gaps to surface
    substitutions: list[str] = Field(default_factory=list)  # honest bridges applied


# ---------------------------------------------------------------- Sponsorship
class SponsorSignal(BaseModel):
    """Task 1.5 output."""
    company: str
    normalized_name: str = ""
    lca_count_3y: int = 0
    most_recent_fy: str = ""
    approval_rate: float | None = None
    likelihood: Literal["high", "medium", "low", "unknown"] = "unknown"
    confidence: Literal["high", "medium", "low"] = "high"  # name-match confidence
    needs_verification: bool = False   # ambiguous match -> human should confirm
    evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- Fit score
class FitScore(BaseModel):
    """Task 1.6 output. Deterministic + LLM-anchored, per blueprint §12/§13."""
    dimensions: dict[str, float] = Field(default_factory=dict)  # skills/exp/loc/...
    deterministic_0_100: float = 0.0
    llm_0_100: float | None = None
    final_0_100: float = 0.0
    final_1_5: float = 0.0
    rationale: str = ""


class ApplyDecision(BaseModel):
    """Task 1.7 output."""
    recommend_apply: bool
    confidence: Literal["high", "medium", "low"] = "medium"
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)   # failed hard knockouts


# ---------------------------------------------------------------- Resume
class ResumeContent(BaseModel):
    """Tailored, still-structured resume before rendering (Task 1.8)."""
    headline: str = ""
    summary: str = ""
    experiences: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    skills: dict[str, list[str]] = Field(default_factory=dict)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)


class ResumeDoc(BaseModel):
    content: ResumeContent
    docx_path: str = ""
    pdf_path: str = ""
    page_count: int = 0


# ---------------------------------------------------------------- Verification
class VerifyReport(BaseModel):
    """Task 1.9/1.10 output. `passed` gates the pipeline."""
    passed: bool = True
    blockers: list[str] = Field(default_factory=list)   # fabrication, parse fail
    warnings: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)


class CoverLetter(BaseModel):
    """Task 1.12 output. Grounded, anti-AI-tell, human-reviews-before-send."""
    company: str = ""
    role: str = ""
    greeting: str = "Dear Hiring Manager,"
    paragraphs: list[str] = Field(default_factory=list)
    closing: str = "Sincerely,"
    signoff_name: str = ""
    text: str = ""                      # full assembled letter
    word_count: int = 0
    passed: bool = True                 # grounding gate (no invented metrics)
    warnings: list[str] = Field(default_factory=list)   # anti-AI-tell lint, etc.


class ATSScore(BaseModel):
    """Task 1.11 output. Transparent keyword/skill-overlap proxy (NOT a real ATS
    score). overall = 0.5*keyword + 0.3*quantification + 0.2*structure."""
    keyword_coverage: float = 0.0        # 0-100 (weighted; hard > soft)
    quantification: float = 0.0          # 0-100 (rewards the ~50-60% band, not 100%)
    structure: float = 0.0               # 0-100 (sections/headings/dates/contact)
    semantic_coverage: float = 0.0       # 0-100 = % of JD requirements evidenced (per-req cosine)
    overall_0_100: float = 0.0
    band: Literal["good", "fair", "weak"] = "weak"
    semantic_method: Literal["lexical", "gemini"] = "lexical"
    missing_keywords: list[str] = Field(default_factory=list)     # hard keywords absent
    weak_requirements: list[str] = Field(default_factory=list)    # JD reqs under-evidenced
    detail: dict[str, Any] = Field(default_factory=dict)
