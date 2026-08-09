"""resumaker - grounded, ATS-optimized resume tailoring from a job-description URL.

The library is organized by domain:
    config/         env-driven settings + constants
    domain/         pydantic schemas (the I/O contracts between stages)
    providers/      external effects: llm/ (registry), scrape/, sources/
    stages/         one module per pipeline step (scrape, structure, ... resume, cover)
    ats/            scoring, semantic coverage, parse-verification, fact-gate, simulation
    pipeline/       the orchestrator (stage DAG) + progress reporting
    enrichment/     durable preferences + house-rules memory
    persistence/    repositories (files canonical, sqlite derived) + caches
    observability/  structured logging, metrics, cost guard
"""

__version__ = "0.1.0"
