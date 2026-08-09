"""Durable enrichment + preferences memory: house rules injected into tailoring every
run, do-not-repeat list, and the append-only enrichment log + source-of-truth updater."""
from resumaker.enrichment.manager import (
    add_do_not_repeat,
    add_house_rule,
    do_not_repeat,
    house_rules_for,
    house_rules_prompt,
    load_house_rules,
    preferences,
    read_enrichment_log,
    record_enrichment,
    summary,
    update_profile_fact,
)
from resumaker.enrichment.proposals import (
    Proposal,
    propose_from_tracker,
    tracked_report_count,
)

__all__ = [
    "house_rules_prompt", "house_rules_for", "do_not_repeat", "load_house_rules",
    "add_house_rule", "add_do_not_repeat", "record_enrichment",
    "read_enrichment_log", "update_profile_fact", "preferences", "summary",
    "propose_from_tracker", "Proposal", "tracked_report_count",
]
