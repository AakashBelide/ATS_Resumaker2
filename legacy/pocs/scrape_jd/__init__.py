"""Task 1.1 - JD scraper.

Tiered strategy (blueprint §15):
  1. Official public ATS JSON APIs (Greenhouse / Lever / Ashby) - free, clean, no key.
  2. Playwright headless fetch + text extraction - for JS-rendered / other pages.
  3. (future) stealth eval: Scrapling / CloakBrowser for bot-protected pages + the
     Phase-3 local test-ATS harness.

Output: RawJD (raw_text + source metadata) -> feeds Task 1.2 (structuring).
"""
from .scraper import RawJD, scrape

__all__ = ["RawJD", "scrape"]
