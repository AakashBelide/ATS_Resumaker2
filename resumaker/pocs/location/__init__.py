"""Task 1.L - JD-aware location presentation (blueprint §6 + Appendix B1)."""
from pocs.location.resolver import (
    LocationPlan,
    LocationPrefs,
    load_prefs,
    resolve_location,
    to_metro,
)

__all__ = ["LocationPlan", "LocationPrefs", "resolve_location", "to_metro", "load_prefs"]
