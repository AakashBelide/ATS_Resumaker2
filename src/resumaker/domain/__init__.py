"""Domain contracts: the Pydantic models exchanged between pipeline stages, plus the
ingestion/persistence records."""
from resumaker.domain.ingestion import (
    BoardRef,
    Company,
    JobRecord,
    RunRecord,
)
from resumaker.domain.schemas import (
    ApplyDecision,
    ATSScore,
    CoverLetter,
    FitScore,
    GapItem,
    GapReport,
    JobPosting,
    KeywordSet,
    Knockout,
    PipelineResult,
    ResumeContent,
    ResumeDoc,
    SponsorSignal,
    VerifyReport,
    WeightedKeyword,
    WorkModel,
)

__all__ = [
    "ApplyDecision", "ATSScore", "CoverLetter", "FitScore", "GapItem", "GapReport",
    "JobPosting", "KeywordSet", "Knockout", "PipelineResult", "ResumeContent",
    "ResumeDoc", "SponsorSignal", "VerifyReport", "WeightedKeyword", "WorkModel",
    "BoardRef", "Company", "JobRecord", "RunRecord",
]
