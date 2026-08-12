"""Board-listing adapters (watchlist ingestion). `get_source(name)` returns an adapter."""
from resumaker.providers.sources.algolia import AlgoliaSource
from resumaker.providers.sources.amazon import AmazonJobsSource
from resumaker.providers.sources.apple import AppleSource
from resumaker.providers.sources.ashby import AshbySource
from resumaker.providers.sources.base import PostingStub, SourceAdapter
from resumaker.providers.sources.breezy import BreezySource
from resumaker.providers.sources.bytedance import ByteDanceSource
from resumaker.providers.sources.dassault import DassaultSource
from resumaker.providers.sources.eightfold import EightfoldSource
from resumaker.providers.sources.goldman import GoldmanSource
from resumaker.providers.sources.google import GoogleSource
from resumaker.providers.sources.greenhouse import GreenhouseSource
from resumaker.providers.sources.ibm import IBMSource
from resumaker.providers.sources.icims import ICIMSSource
from resumaker.providers.sources.jibe import JibeApplySource
from resumaker.providers.sources.lever import LeverSource
from resumaker.providers.sources.mckinsey import McKinseySource
from resumaker.providers.sources.meta import MetaSource
from resumaker.providers.sources.microsoft import MicrosoftSource
from resumaker.providers.sources.oracle_cloud import OracleCloudSource
from resumaker.providers.sources.paradox import ParadoxSource
from resumaker.providers.sources.pcsx import PcsxSource
from resumaker.providers.sources.phenom import PhenomSource
from resumaker.providers.sources.radancy import RadancySource
from resumaker.providers.sources.recruitee import RecruiteeSource
from resumaker.providers.sources.smartrecruiters import SmartRecruitersSource
from resumaker.providers.sources.tesla import TeslaSource
from resumaker.providers.sources.wayfair import WayfairSource
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
    JibeApplySource.source: JibeApplySource(),
    RadancySource.source: RadancySource(),
    AppleSource.source: AppleSource(),
    ByteDanceSource.source: ByteDanceSource(),
    DassaultSource.source: DassaultSource(),
    MicrosoftSource.source: MicrosoftSource(),
    GoogleSource.source: GoogleSource(),
    MetaSource.source: MetaSource(),
    TeslaSource.source: TeslaSource(),
    PcsxSource.source: PcsxSource(),
    ParadoxSource.source: ParadoxSource(),
    IBMSource.source: IBMSource(),
    ICIMSSource.source: ICIMSSource(),
    WayfairSource.source: WayfairSource(),
    AlgoliaSource.source: AlgoliaSource(),
    RecruiteeSource.source: RecruiteeSource(),
    BreezySource.source: BreezySource(),
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
