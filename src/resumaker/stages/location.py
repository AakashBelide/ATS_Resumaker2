"""JD-aware location presentation (Task 1.L, blueprint §6 + Appendix B1).

Location is a HARD gate, not cosmetic: ~43% of recruiters apply a location radius
filter (commonly "within 50 miles") BEFORE a human reads anything, and it doubles
as a ranking signal. This module decides how to present the candidate's location
on a per-JD basis - HONESTLY. It never spoofs the candidate into a metro they are
not in / not moving to (that collides with the resume<->LinkedIn triangulation
check, Appendix B9, and is caught at background check, B10).

Deterministic, zero-LLM ($0). Rules implemented:
  - Normalize the candidate's own city UP to its major metro (Broomfield -> Denver).
  - Normalize the JD city the same way, then compare metros:
      same metro                       -> present as LOCAL (real metro).
      JD metro in willing-relocation   -> "Relocating to <metro> (<timeframe>)".
      remote + eligible + open         -> "<metro> (Open to Remote)".
      remote but state/timezone barred -> keep real metro + WARN (likely hard fail).
      different metro, not relocating   -> keep real metro + WARN (geo radius gate).
  - NEVER emit a full street address, a bare ZIP, or a bare "Remote" (all §6 don'ts).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from resumaker.domain import JobPosting, WorkModel
from resumaker.persistence import profile as prof

# --- US state name -> USPS abbreviation (for parsing "Quincy, Massachusetts") ---
_STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC", "washington, d.c.": "DC",
}
_ABBRS = set(_STATE_ABBR.values())

# Eastern-timezone states (Boston = ET); used for the remote timezone heuristic.
_ET_STATES = {"ME", "NH", "VT", "MA", "RI", "CT", "NY", "NJ", "PA", "DE", "MD",
              "DC", "VA", "WV", "NC", "SC", "GA", "FL", "OH", "MI", "IN", "KY"}

# --- Suburb / satellite city -> major metro anchor (blueprint §6: use the metro,
#     e.g. "Denver, CO" not the suburb "Broomfield, CO"). Only UPGRADES a smaller
#     city to its genuine metro; unknown cities pass through unchanged (honest). ---
_METRO = {
    # Greater Boston
    ("quincy", "MA"): "Boston, MA", ("cambridge", "MA"): "Boston, MA",
    ("somerville", "MA"): "Boston, MA", ("waltham", "MA"): "Boston, MA",
    ("burlington", "MA"): "Boston, MA", ("newton", "MA"): "Boston, MA",
    ("brookline", "MA"): "Boston, MA", ("medford", "MA"): "Boston, MA",
    # Denver
    ("broomfield", "CO"): "Denver, CO", ("boulder", "CO"): "Denver, CO",
    ("aurora", "CO"): "Denver, CO", ("lakewood", "CO"): "Denver, CO",
    # Seattle
    ("bellevue", "WA"): "Seattle, WA", ("redmond", "WA"): "Seattle, WA",
    ("kirkland", "WA"): "Seattle, WA",
    # SF Bay Area (peninsula / south bay anchor to San Jose or SF honestly)
    ("mountain view", "CA"): "San Jose, CA", ("palo alto", "CA"): "San Jose, CA",
    ("sunnyvale", "CA"): "San Jose, CA", ("cupertino", "CA"): "San Jose, CA",
    ("menlo park", "CA"): "San Jose, CA", ("santa clara", "CA"): "San Jose, CA",
    ("oakland", "CA"): "San Francisco, CA", ("south san francisco", "CA"): "San Francisco, CA",
    # NYC
    ("jersey city", "NJ"): "New York, NY", ("newark", "NJ"): "New York, NY",
    ("brooklyn", "NY"): "New York, NY", ("long island city", "NY"): "New York, NY",
    # Dallas / Austin / Texas
    ("plano", "TX"): "Dallas, TX", ("irving", "TX"): "Dallas, TX",
    ("round rock", "TX"): "Austin, TX",
    # Others
    ("santa monica", "CA"): "Los Angeles, CA", ("pasadena", "CA"): "Los Angeles, CA",
    ("bellevue", "NE"): "Omaha, NE", ("bothell", "WA"): "Seattle, WA",
    ("alpharetta", "GA"): "Atlanta, GA", ("bellevue", "TN"): "Nashville, TN",
}


@dataclass
class LocationPrefs:
    """Candidate location preferences (persisted by Task 1.13 in preferences.json)."""
    open_to_remote: bool = True
    willing_to_relocate: bool = False
    # relocate_anywhere: candidate will move to ANY metro (own expense) -> present
    # the job's metro automatically for every out-of-metro role.
    relocate_anywhere: bool = False
    relocation_metros: list[str] = field(default_factory=list)  # explicit targets
    relocation_timeframe: str = ""                              # e.g. "Q3 2026"
    # How to render the location for a relocation role:
    #   bare_metro        -> "New York, NY"                (reads local; best filter)
    #   target_metro_open -> "New York, NY (Open to Relocation)"
    #   base_relocating   -> "Boston, MA | Relocating to New York, NY"
    relocation_display: str = "bare_metro"
    # None => authorized in all US states (F-1 CPT/OPT is nationwide); a list
    # restricts (e.g. an already-sponsored candidate tied to specific states).
    authorized_states: list[str] | None = None


def _reloc_display(base_metro: str, job_metro: str, prefs: LocationPrefs) -> str:
    tf = f" ({prefs.relocation_timeframe})" if prefs.relocation_timeframe else ""
    style = prefs.relocation_display
    if style == "target_metro_open":
        return f"{job_metro} (Open to Relocation)"
    if style == "base_relocating":
        return f"{base_metro} | Relocating to {job_metro}{tf}"
    return job_metro  # bare_metro (default): reads fully local


@dataclass
class LocationPlan:
    display: str                     # the string to render on the contact line
    strategy: str                    # local|open_to_remote|relocating|non_local|remote_ineligible|unknown_jd
    is_local: bool = False
    passes_geo_filter: bool = True   # would this honestly clear a radius/eligibility gate
    candidate_metro: str = ""
    job_metro: str = ""
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _parse_city_state(text: str) -> tuple[str, str]:
    """Extract ('City', 'ST') from a free-form location string. Returns ('','') if
    no US city/state is confidently found (e.g. 'Remote', 'United States')."""
    if not text:
        return "", ""
    t = re.sub(r"\s+", " ", text.strip())
    # "City, ST" or "City, State Name"
    m = re.search(r"([A-Za-z][A-Za-z .'-]+?),\s*([A-Za-z .]{2,})", t)
    if m:
        city = m.group(1).strip()
        st_raw = m.group(2).strip().rstrip(".")
        st = st_raw.upper() if st_raw.upper() in _ABBRS else \
            _STATE_ABBR.get(st_raw.lower(), "")
        if st:
            return city, st
    # bare state at the end ("... Massachusetts")
    for name, abbr in _STATE_ABBR.items():
        if re.search(rf"\b{re.escape(name)}\b", t.lower()):
            return "", abbr
    m2 = re.search(r"\b([A-Z]{2})\b", t)
    if m2 and m2.group(1) in _ABBRS:
        return "", m2.group(1)
    return "", ""


def to_metro(city: str, state: str) -> str:
    """Upgrade a suburb/satellite city to its major metro; else 'City, ST'."""
    if not state:
        return city or ""
    key = (city.strip().lower(), state)
    if key in _METRO:
        return _METRO[key]
    return f"{city}, {state}" if city else state


def _remote_eligible(job: JobPosting, cand_state: str,
                     prefs: LocationPrefs) -> tuple[bool, str]:
    """Can the candidate honestly take this remote role from their state/timezone?"""
    restr = (job.remote_restriction or "").strip()
    # explicit state authorization list (already-sponsored / payroll constraints)
    if prefs.authorized_states is not None and cand_state \
            and cand_state not in prefs.authorized_states:
        return False, (f"Remote role but you are authorized only in "
                       f"{prefs.authorized_states}; you are in {cand_state}.")
    if not restr:
        return True, ""
    low = restr.lower()
    # a specific state named that is NOT the candidate's -> ineligible
    named = {a for name, a in _STATE_ABBR.items() if re.search(rf"\b{re.escape(name)}\b", low)}
    named |= {a for a in _ABBRS if re.search(rf"\b{a}\b", restr)}
    if named and cand_state and cand_state not in named:
        return False, (f"Remote role restricted to {sorted(named)}; "
                       f"you are in {cand_state}.")
    # timezone constraint heuristic (Boston = ET)
    if re.search(r"\b(pt|pst|pacific|ct|cst|central|mt|mst|mountain)\b", low) \
            and not re.search(r"\b(et|est|eastern)\b", low):
        if cand_state in _ET_STATES:
            return True, (f"Remote timezone ask ('{restr}') differs from your ET; "
                          f"verify overlap is workable.")
    return True, ""


def resolve_location(job: JobPosting, *, candidate_location: str | None = None,
                     prefs: LocationPrefs | None = None) -> LocationPlan:
    p = prof.load_profile()
    candidate_location = candidate_location or p.get("contact", {}).get("location", "")
    prefs = prefs or load_prefs()

    c_city, c_state = _parse_city_state(candidate_location)
    cand_metro = to_metro(c_city, c_state) or candidate_location
    j_city, j_state = _parse_city_state(job.location or "")
    job_metro = to_metro(j_city, j_state) if (j_city or j_state) else ""

    plan = LocationPlan(display=cand_metro, strategy="local",
                        candidate_metro=cand_metro, job_metro=job_metro)

    # --- Remote roles: state/timezone eligibility drives presentation ---
    if job.work_model == WorkModel.remote:
        ok, reason = _remote_eligible(job, c_state, prefs)
        if not ok:
            plan.strategy = "remote_ineligible"
            plan.passes_geo_filter = False
            plan.warnings.append(reason)
            return plan
        if reason:
            plan.notes.append(reason)
        if prefs.open_to_remote:
            plan.display = f"{cand_metro} (Open to Remote)"
            plan.strategy = "open_to_remote"
        plan.is_local = (job_metro == cand_metro)
        return plan

    # --- Onsite / hybrid / unknown: compare metros ---
    if not job_metro:
        plan.strategy = "unknown_jd"
        plan.notes.append("JD location is unspecified; presenting your real metro.")
        return plan

    if job_metro == cand_metro:
        plan.strategy = "local"
        plan.is_local = True
        return plan

    # different metro: present the job's metro if the candidate will move there -
    # either because it's an explicit target OR they relocate anywhere (own expense).
    reloc_norm = {m.strip().lower() for m in prefs.relocation_metros}
    explicit = prefs.willing_to_relocate and job_metro.lower() in reloc_norm
    if explicit or prefs.relocate_anywhere:
        plan.display = _reloc_display(cand_metro, job_metro, prefs)
        plan.strategy = "relocating"
        plan.passes_geo_filter = True
        if prefs.relocation_display == "bare_metro":
            plan.notes.append(
                f"Presenting target metro '{job_metro}' as your location (you relocate "
                f"anywhere at own expense). Set your LinkedIn location to this metro or "
                f"'Open to relocating' so the resume<->LinkedIn check stays consistent "
                f"(Appendix B9).")
        else:
            plan.notes.append(f"Presenting relocation to {job_metro}.")
        return plan

    plan.strategy = "non_local"
    plan.passes_geo_filter = False
    wm = job.work_model.value if job.work_model != WorkModel.unknown else "onsite/hybrid"
    plan.warnings.append(
        f"JD is {wm} in {job_metro} but you are in {cand_metro}. ~43% of recruiters "
        f"apply a location-radius filter first, so this is likely a hard geo gate. "
        f"Enable relocate_anywhere or add '{job_metro}' to relocation_metros if you "
        f"would genuinely move; otherwise consider skipping.")
    return plan


def load_prefs() -> LocationPrefs:
    """Read location preferences from the Task 1.13 preferences store
    (data/profile/preferences.json), else safe defaults for an F-1 CPT/OPT candidate."""
    loc = (prof.load_preferences() or {}).get("location", {})
    return LocationPrefs(
        open_to_remote=loc.get("open_to_remote", True),
        willing_to_relocate=loc.get("willing_to_relocate", False),
        relocate_anywhere=loc.get("relocate_anywhere", False),
        relocation_metros=list(loc.get("relocation_metros", [])),
        relocation_timeframe=loc.get("relocation_timeframe", ""),
        relocation_display=loc.get("relocation_display", "bare_metro"),
        authorized_states=loc.get("authorized_states"),
    )
