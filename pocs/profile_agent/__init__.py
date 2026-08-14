"""Profile chat-agent POC.

Human-in-the-loop agent that (1) onboards a candidate from a resume/LinkedIn PDF, (2) enriches
their profile through conversation, and (3) clarifies JD<->profile gaps at match time before
generating a resume - then re-matches so the fit score reflects the enriched profile.

The agent is a *scribe, not an author*: a fact only enters profile.json when the USER asserts it,
via the audited `enrichment.manager.update_profile_fact()`. Nothing it writes bypasses the fact
gate. See RESEARCH.md for the full design and the reference-repo grounding.
"""
