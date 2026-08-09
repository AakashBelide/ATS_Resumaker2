"""Single-JD scrapers (public ATS APIs first, Playwright fallback)."""
from resumaker.providers.scrape.scraper import RawJD, scrape

__all__ = ["RawJD", "scrape"]
