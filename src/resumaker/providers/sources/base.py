"""Board-listing seam for the watchlist/ingestion subsystem (RI).

Where `scrape/` fetches ONE JD by URL, a `SourceAdapter` LISTS all current postings for a
company's board (by its per-source token). The scheduler polls these, dedupes into `jobs`,
and feeds new/changed ones to the pipeline. Defined now so the contract is stable; adapters
land in the RI phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PostingStub:
    """A lightweight listing entry (enough to dedupe + decide whether to fetch fully)."""
    source: str
    external_id: str
    url: str = ""
    title: str = ""
    location: str = ""
    updated_at: str = ""
    extra: dict = field(default_factory=dict)


class SourceAdapter(Protocol):
    source: str

    def list_postings(self, token: str, **kwargs: str) -> list[PostingStub]:
        """Return all current postings for the given board token."""
        ...
