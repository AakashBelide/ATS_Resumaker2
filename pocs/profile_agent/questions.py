"""Question banks the agent selects from.

- PREFERENCE_QUESTIONS: the small, objective onboarding set (Flow 1). Batchable, since they're not
  evidential claims about the candidate's work.
- PROBE_BANK: evidential probes (Flow 2/3), grouped by theme. The agent asks the FEWEST that target
  actual thin spots - never the whole bank. Sourced from career-ops `modes/interview.md` Steps 3-4.
"""
from __future__ import annotations

# ---- Flow 1: basic preference questions -----------------------------------
# Each: (key, prompt, kind) where kind routes the write. `pref` -> preferences doc; `house_rule` ->
# enrichment.manager.add_house_rule; `profile` -> a profile.json path.
PREFERENCE_QUESTIONS: list[dict] = [
    {"key": "target_roles",
     "q": "Which roles are you targeting? (e.g. AI Engineer, ML Engineer, GenAI/Agentic Engineer, "
          "Data Scientist, Data Engineer)", "kind": "pref"},
    {"key": "seniority",
     "q": "What seniority are you targeting? (intern / new-grad / mid / senior / staff)", "kind": "pref"},
    {"key": "work_model",
     "q": "Preferred work model (onsite / hybrid / remote), and your current base location?", "kind": "pref"},
    {"key": "relocation",
     "q": "Are you open to relocation? If so, which metros?", "kind": "pref"},
    {"key": "work_authorization",
     "q": "Work authorization: do you need visa sponsorship now or in the future?", "kind": "profile"},
    {"key": "compensation",
     "q": "Target compensation range and hard minimum (with currency)?", "kind": "pref"},
    {"key": "exclusions",
     "q": "Any hard 'no' filters? (industries or companies to exclude)", "kind": "pref"},
    {"key": "style_rules",
     "q": "Any style rules to always remember? (e.g. 'no em-dashes', 'combine the Bajaj roles', "
          "'inline location')", "kind": "house_rule"},
]

# ---- Flow 2/3: evidential probing bank -------------------------------------
PROBE_BANK: dict[str, list[str]] = {
    "impact_metrics": [
        "What measurably changed because of this project - a %, $, time saved, latency, throughput, "
        "or user/record count?",
        "Before vs after: what was the baseline, and what did it become?",
        "How many people, teams, records, or requests did it touch?",
        "If you can't measure it, how would you frame the impact qualitatively "
        "(e.g. 'enabled 12 devs to ship 3x faster')?",
    ],
    "tech_stack": [
        "Which languages, frameworks, databases, and cloud services did you actually use here?",
        "What tools do you know that aren't on your resume yet (side projects, coursework, POCs)?",
        "Model or framework specifics worth naming (LangGraph, MCP, Qdrant, Databricks, ...)?",
    ],
    "role_scope": [
        "What was your exact title and level, and how big was the team?",
        "Were you the builder, the lead/architect, or the reviewer?",
        "End-to-end ownership or one slice? Which slice?",
    ],
    "stakeholders_comm": [
        "Who used or depended on this (internal teams, external customers, executives)?",
        "Did you present results, write docs, or run demos? To whom?",
        "Any cross-functional collaboration (PM, data, security, infra)?",
    ],
    "business_domain": [
        "What business problem did this solve, and in what domain (fintech, telecom, healthcare, ...)?",
        "What domain terms or regulations were involved (fraud, delinquency, HIPAA, KYC)?",
    ],
    "achievements": [
        "Any awards, promotions, patents filed, publications, or talks?",
        "Certifications or courses completed recently?",
        "Anything you're proud of that never made it onto a resume?",
    ],
}


def flat_probes() -> list[str]:
    return [q for group in PROBE_BANK.values() for q in group]
