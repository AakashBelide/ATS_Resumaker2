"""Task 1.5 - US sponsorship-likelihood scorer (blueprint §14).

Deterministic, $0 (no LLM). Backed by the USCIS H-1B Employer Data Hub
(petition approve/deny outcomes per employer per fiscal year). Employer-name
normalization + rapidfuzz matching bridge query companies to the gov data since
the tax-ID join is unavailable (USCIS exposes only the last-4 of the EIN).

Output: SponsorSignal (core.schemas).
"""
from .scorer import (
    SponsorIndex,
    build_index,
    get_index,
    match_employer,
    normalize_name,
    score_company,
    sponsor_signal,
)

__all__ = [
    "SponsorIndex",
    "build_index",
    "get_index",
    "match_employer",
    "normalize_name",
    "score_company",
    "sponsor_signal",
]
