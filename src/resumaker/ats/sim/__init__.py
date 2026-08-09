"""Offline ATS + recruiter simulation (parse fidelity, Boolean surfacing, BM25 ranking)
and the Affinda industry-parser oracle. NOT part of the per-JD pipeline - a validation
harness run periodically."""
from resumaker.ats.sim.sim import (
    ParseCard,
    bm25_scores,
    boolean_surface,
    parse_resume,
    rank_pool,
)

__all__ = ["ParseCard", "parse_resume", "bm25_scores", "boolean_surface", "rank_pool"]
