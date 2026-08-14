# Profile chat-agent (POC)

A human-in-the-loop agent that builds and enriches a candidate's profile through conversation, and
clarifies JD↔profile gaps at match time before a resume is generated. CLI-first (like the other
POCs); an API/web wiring plan is in [RESEARCH.md](RESEARCH.md).

**Core principle — the agent is a scribe, not an author.** A fact only enters `profile.json` when
the *user asserts it*: every proposed write must carry a `source_quote` that is a verbatim span of
the user's own words, and every write goes through the audited
`enrichment.manager.update_profile_fact()`. Nothing the agent writes bypasses `ats/fact_gate.py`.

## Three flows

| Flow | What it does | Entry |
|------|--------------|-------|
| **1. Intake** | Parse a resume (+ optional LinkedIn PDF) into our `profile.json` shape (zero-invention), detect thin spots, ask basic preferences. | `intake <resume>` |
| **2. Enhance** | Chat: user gives extra info (free text / JSON dump / probe answers) → grounded profile updates. | `enhance` → `say` |
| **3. Gap-chat** | Seeded from a match's `report.json` gaps; user confirms real evidence → **re-match → generate**. Score rises only because real evidence flips gap items. | `gapchat <report_run_id>` → `say … /generate` |

## Slash commands (parsed deterministically, before the LLM)

`/help` · `/skip` (drop pending) · `/done` (finish) · `/generate` (Flow 3: re-match then generate) ·
`/stop` (hard abort, discard unconfirmed) · `/undo` (revert last applied write).

Loop is bounded: **40 turns**, **30 min**, **$5 budget**, a no-progress guard, and one active run per
profile. Each turn is a single `complete_json()` call (`--max-turns 1 --tools ""`) — no ReAct loop.

## Run it

```bash
# Flow 1 — intake (writes a parsed profile to the run dir; promote is explicit)
uv run python -m pocs.profile_agent.cli intake Resources/Aakash_Belide_Resume.docx \
      --linkedin Resources/LinkedIn_Profile.pdf
uv run python -m pocs.profile_agent.cli intake-apply <run_id>     # -> canonical profile.json

# Flow 2 — enhancement chat
uv run python -m pocs.profile_agent.cli enhance
uv run python -m pocs.profile_agent.cli say <run_id> "At Granite I stood up Qdrant and cut latency ~40%"
uv run python -m pocs.profile_agent.cli say <run_id> "yes"        # confirm
uv run python -m pocs.profile_agent.cli say <run_id> "/done"

# Flow 3 — gap clarification -> re-match -> generate (needs a completed match run_id)
uv run python -m pocs.profile_agent.cli gapchat <report_run_id>
uv run python -m pocs.profile_agent.cli say <run_id> "Yes, I used Kafka at Bajaj for the fraud stream"
uv run python -m pocs.profile_agent.cli say <run_id> "/generate"
```

## Reused (not reimplemented)

`persistence.profile` (load/save), `enrichment.manager` (`update_profile_fact`, `add_house_rule`,
`record_enrichment`), `enrichment.proposals`, `stages.gap` / `stages.role_fit`,
`pipeline.run_pipeline` (`match_only`, reusable `gap`), `providers.llm.get_provider`,
`ats.fact_gate`. See RESEARCH.md Part B for the exact call sites.

## Tests

`uv run pytest pocs/profile_agent/eval/ -q` — deterministic coverage of slash parsing, the
anti-fabrication quote gate, apply/undo, thin-spot detection, and a full enhance turn via a fake LLM
(no network).

## Files

`agent.py` runtime (turns, slash, caps, apply/undo) · `intake.py`/`enhance.py`/`gapchat.py` flows ·
`prompts.py` · `questions.py` (preference + probe banks) · `store.py` run state · `cli.py`.
