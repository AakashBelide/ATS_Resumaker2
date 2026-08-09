"""Board-listing adapters (watchlist ingestion). `get_source(name)` returns an adapter."""
from resumaker.providers.sources.amazon import AmazonJobsSource
from resumaker.providers.sources.ashby import AshbySource
from resumaker.providers.sources.base import PostingStub, SourceAdapter
from resumaker.providers.sources.eightfold import EightfoldSource
from resumaker.providers.sources.goldman import GoldmanSource
from resumaker.providers.sources.greenhouse import GreenhouseSource
from resumaker.providers.sources.lever import LeverSource
from resumaker.providers.sources.mckinsey import McKinseySource
from resumaker.providers.sources.oracle_cloud import OracleCloudSource
from resumaker.providers.sources.phenom import PhenomSource
from resumaker.providers.sources.smartrecruiters import SmartRecruitersSource
from resumaker.providers.sources.workday import WorkdaySource

_SOURCES: dict[str, SourceAdapter] = {
    GreenhouseSource.source: GreenhouseSource(),
    LeverSource.source: LeverSource(),
    AshbySource.source: AshbySource(),
    WorkdaySource.source: WorkdaySource(),
    EightfoldSource.source: EightfoldSource(),
    AmazonJobsSource.source: AmazonJobsSource(),
    OracleCloudSource.source: OracleCloudSource(),
    SmartRecruitersSource.source: SmartRecruitersSource(),
    McKinseySource.source: McKinseySource(),
    GoldmanSource.source: GoldmanSource(),
    PhenomSource.source: PhenomSource(),
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
