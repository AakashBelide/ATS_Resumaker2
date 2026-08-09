"""Sponsorship likelihood (deterministic, $0). Backed by the USCIS H-1B Employer Data
Hub; JD-explicit stance overrides company history in `resolve`."""
from resumaker.stages.sponsorship.scorer import (
    SponsorIndex,
    build_index,
    get_index,
    match_employer,
    normalize_name,
    score_company,
    sponsor_signal,
)

__all__ = [
    "SponsorIndex", "build_index", "get_index", "match_employer",
    "normalize_name", "score_company", "sponsor_signal",
]
