# Agentic auto-onboarding — architecture & design notes

How the onboarder is structured, how the agents work, how outcomes are decided, and why the
"parallel throwaway sandbox" model is affordable. Companion to [README.md](README.md) (how-to).

## Multi-role, not a swarm

It's "multi-agentic" in the sense of a few **specialized agent roles**, each a separate sandboxed
`claude -p` invocation with its own prompt/tools/goal — wired together by a **deterministic
orchestrator**. The intelligence sits at 2 points; everything around it is plain, verifiable code.
That's deliberate: cheaper and more robust than many agents negotiating at once.

### Agents (roles)
| Agent | When | Goal | How it works |
|---|---|---|---|
| **Resolver** | every onboarding | company → validated BoardRef | one sandboxed `claude -p`, internally loops tool calls (fetch/curl/ats_probe) up to `max_turns`, fingerprints the platform, returns a JSON contract |
| **Author** | only when the platform has **no adapter** | draft a new adapter + fixture + test | separate sandboxed `claude -p`, different mandate, writes files to a mounted `/out` |
| **Reviser** | when the gate fails | fix the draft from gate feedback | the author role re-invoked with the failure notes (bounded loop, not a new agent) |

Per onboarding: usually **1** agent (resolver). New platform: **2** (resolver → author) + a few
reviser iterations. Horizontally, onboarding N companies = **N resolver agents in parallel**, each
in its own throwaway sandbox.

### NOT agents (deterministic scaffolding — the other half)
- **Orchestrator** — Python state machine: deterministic-first → resolver → author → gate; tracks
  status; enforces caps; handles `needs_input`. ([orchestrator.py](orchestrator.py))
- **Deterministic resolver** — slug-probe, $0, no LLM, handles the common cases with no sandbox.
- **Validator** — calls the *real* adapter registry to verify a BoardRef.
- **Gate** — static AST scan + sandboxed offline test + live check. ([adapter_writer/gate.py](adapter_writer/gate.py))

## Outcome model — "the agent proposes; deterministic checks dispose"

No terminal state is the agent's self-assessment. Each is decided from a verifiable signal or a
hard cap, so the system never trusts an unverified "done" and never loops forever:

| Outcome | Meaning | How it's decided (NOT by the agent's say-so) |
|---|---|---|
| **resolved** | success | controller re-validates the BoardRef via the **real adapter** (`list_postings` ≥ 1 posting). Wrong guesses are rejected. |
| **needs_input** | achievable *with a human answer* | agent can't proceed without a careers URL / board token → emits a question; run pauses. |
| **new-platform** | achievable *with new code* | resolver names a platform not in the registry → routed to the **author**, whose success is decided by the **gate**, not the agent. |
| **unresolved** | unachievable for now | agent exhausted bounded attempts (`max_turns`) with no fingerprint/useful question, or validation kept failing. Parked for a human. |
| **killed / stopped** | aborted | a time / budget / manual guard fired. An operator/watchdog decision, not a goal outcome. |

Author success is likewise decided by the gate (static-scan clean **and** offline fixture test
pass **and** live check ≥ 1 posting) — verifiable, not "the agent said the code is good."

## Compute & scaling — is "parallel throwaway sandboxes" too heavy?

Short answer: **no, in practice** — for five reasons:

1. **Onboarding is a rare, one-time COLD path.** You onboard a company once; then it lives in the
   watchlist forever and ingestion takes over. This is not a per-request hot path, so per-run cost
   barely matters. Don't optimize a cold path.
2. **Deterministic-first means most onboards never launch a sandbox.** The $0 slug-probe resolves
   the common ATS cases (greenhouse/lever/ashby) with no container and no LLM. Only the hard tail
   escalates to the agent+sandbox.
3. **The sandbox is I/O-bound, not CPU-bound.** The heavy compute (LLM inference) runs on
   Anthropic's servers. Locally the container just runs the CLI client + light HTTP — it spends
   almost all its time *waiting* on the LLM and the ATS APIs. RAM is capped (512MB–1GB) and the
   Node client uses a few hundred MB; CPU is near-idle while waiting.
4. **Concurrency is capped to a small pool.** You run a handful at a time (e.g. 2–5) and queue the
   rest — the existing pipeline already uses a `ThreadPoolExecutor(max_workers=2)`. The real
   governor is **LLM rate limits + your budget caps**, not local compute.
5. **Production uses a process-light sandbox, not Docker-per-run.** Docker is the portable POC
   choice. On the Linux VM the runner swaps to **bubblewrap** (what Claude Code itself uses):
   no daemon, near-instant startup, per-sandbox cost ≈ a process. Throwaway-per-run is then
   basically free, and "fresh per run" is a *security* property, not a compute burden.

Where it *would* get heavy: onboarding thousands simultaneously, or putting the agent on a hot
per-request path — neither applies here. The one-time disk cost is the ~615 MB agent image.

**Net:** throwaway ≠ expensive. Short-lived + thin + I/O-bound + rare + concurrency-capped +
(prod) bubblewrap ⇒ the resource cost is dominated by remote LLM tokens (already bounded by the
turn/time/budget caps), not by local sandboxes.
