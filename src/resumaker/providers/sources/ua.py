"""Shared User-Agent for the clean public-JSON board APIs.

An honest, descriptive UA (rather than a spoofed browser string) is the polite convention
for these endpoints - Lever's robots.txt explicitly welcomes crawlers at 1 req/s, and all
four ATS APIs return 200 to a plain UA. Workday is the exception: it goes through curl_cffi
with Chrome TLS impersonation (see workday.py)."""
UA = "resumaker/1.0 (personal job watchlist)"
