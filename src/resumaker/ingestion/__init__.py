"""Watchlist ingestion: auto-onboard companies, dedupe postings, schedule polls, notify."""
from resumaker.ingestion.discovery import DiscoveryFilters, DiscoveryResult, discover
from resumaker.ingestion.onboard import OnboardResult, resolve
from resumaker.ingestion.service import IngestResult, ingest_all, ingest_company

__all__ = ["resolve", "OnboardResult", "ingest_company", "ingest_all", "IngestResult",
           "discover", "DiscoveryFilters", "DiscoveryResult"]
