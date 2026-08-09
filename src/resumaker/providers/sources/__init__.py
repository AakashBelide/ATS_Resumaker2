"""Board-listing adapters (watchlist ingestion). `get_source(name)` returns an adapter."""
from resumaker.providers.sources.base import PostingStub, SourceAdapter
from resumaker.providers.sources.greenhouse import GreenhouseSource

_SOURCES: dict[str, SourceAdapter] = {
    GreenhouseSource.source: GreenhouseSource(),
}


def get_source(name: str) -> SourceAdapter:
    try:
        return _SOURCES[name]
    except KeyError:
        raise ValueError(
            f"unknown source {name!r}; available: {sorted(_SOURCES)}") from None


def available_sources() -> list[str]:
    return sorted(_SOURCES)


__all__ = ["PostingStub", "SourceAdapter", "get_source", "available_sources"]
