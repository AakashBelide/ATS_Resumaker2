# POC — Agentic auto-onboarding (sandboxed Claude CLI)

Standalone proof-of-concept for the onboarding MVP: given a **company name** (and optionally a
**careers URL**), resolve its ATS job board **agentically** — a Claude CLI agent with real tools
+ shell that dynamically probes, parses, and self-heals — while running inside a **lightweight,
durable, secure sandbox**. Nothing here touches the live backend / frontend / extension.

> Status: **Phase A (sandbox) built + verified.** Phase B (agent loop + async human-in-loop)
> built; live eval pending a Claude auth token in the box. Phase C (integration/DB plan) = docs.

## Why a sandbox at all
The agent acts on **attacker-controlled scraped web content** (careers pages), so a prompt
injection could try to make it exfiltrate data or run commands. We do **not** rely on the model
behaving or on prompt guards as the security boundary. The boundary is the OS/container. Prompt
discipline + the PreToolUse hook are hardening on top.

## Architecture
```
host (orchestrator)                          disposable sandbox (per run, --rm)
─────────────────────                        ─────────────────────────────────
run_onboarding(name, url)
  │  1) deterministic-first  ── reuse src/resumaker onboard.resolve (fast, $0, no LLM)
  │        miss ↓
  │  2) agent fallback  ─────────────────►   resolver container
  │                                            • non-root, read-only rootfs, /work+/tmp tmpfs
  │                                            • cap-drop ALL, no-new-privileges, pid/mem caps
  │                                            • NO host mounts (no repo, no .env, no secrets)
  │                                            • only egress = the proxy (allow-list)
  │                                            claude -p  (tools: Bash + fetch + ats_probe)
  │                                              + PreToolUse hook (in-box policy)
  │  3) host re-validates the board ref  ◄──   final JSON: resolved | needs_input | unresolved
  ▼
status.json + events.jsonl  (frontend polls; pops a dialog when state == needs_input)
```
Two networks enforce "egress only through the allow-list proxy": the agent sits on an
`internal: true` Docker network (no NAT/internet); the proxy bridges that to the outside and
returns **403 for any host not on the allow-list** (ATS hosts + `api.anthropic.com` + the one
careers host added per run via `EXTRA_ALLOW`).

## Security model — verified (Phase A)
`python -m pocs.agentic_onboard.cli containment` (or `eval/containment_test.py`) proves, against
real Docker, all of:
- non-root (uid 10001); rootfs **read-only**; only `/work`+`/tmp` writable (tmpfs)
- allow-listed egress works (greenhouse API → 200; proxy logs `ALLOW`)
- **non-allow-listed egress blocked** (example.com → 000; proxy logs `DENY`)
- per-run `EXTRA_ALLOW` opens exactly one extra host, nothing else
- **no `.env` and no `resumaker` source anywhere in the box**

Defense-in-depth layers: **L1** container isolation + egress allow-list (the wall) · **L2**
`--dangerously-skip-permissions` is safe *because* of the sandbox, with a **PreToolUse hook**
([agent/hook_policy.py](agent/hook_policy.py)) blocking credential-path access / raw network
tools / destructive cmds / writes outside `/work`, and `WebFetch`/`WebSearch` disabled so all
fetching goes through our auditable tool · **L3** untrusted-content discipline in the system
prompt · **L4** host re-validates the agent's board ref before trusting it.

## Deterministic-first, agent-fallback (chosen)
The deterministic slug-probe already resolves the common ATS cases in milliseconds at $0 with
**zero injection surface** (it only hits known ATS APIs). We only pay for / expose the agent on
the hard tail. Toggle with `--no-agent` to see the deterministic path alone.

## Setup (one-time) — Claude auth in the box
The sandboxed CLI uses your **subscription** via a long-lived OAuth token (no per-token cost):
```bash
claude setup-token                 # opens a browser; prints a token
mkdir -p pocs/agentic_onboard/.secrets
printf '%s' '<the-token>' > pocs/agentic_onboard/.secrets/claude_oauth_token
```
`.secrets/` is gitignored. The token is forwarded into the container **by name only** (never on a
command line or in a log). On a headless VM, run `setup-token` locally and copy the token over.

## Run
```bash
# security proof (no auth needed)
uv run python -m pocs.agentic_onboard.cli containment

# resolve a company (deterministic first, then the sandboxed agent)
uv run python -m pocs.agentic_onboard.cli resolve "Ramp"
uv run python -m pocs.agentic_onboard.cli resolve "Some Co" --careers-url https://careers.someco.com

# human-in-the-loop: if a run pauses in needs_input, answer it
uv run python -m pocs.agentic_onboard.cli provide-input <run_id> "https://careers.someco.com/jobs"

# watch a run's progress (status.json / events.jsonl)
uv run python -m pocs.agentic_onboard.cli watch <run_id>
```

## Layout
```
sandbox/      compose.yml (2 nets) · Dockerfile.{proxy,sandbox,agent} · proxy.py · allowlist.txt · runner.py
agent/        system_prompt.md · hook_policy.py · claude-settings.json · resolve.py · tools/{ats_probe,fetch}.py
eval/         containment_test.py
orchestrator.py   deterministic-first → agent-fallback → needs_input pause/resume; status.json/events.jsonl
cli.py
```

## Production notes (for the eventual free VM)
- **Host:** Oracle Cloud *Always Free* ARM (up to 4 cores / 24 GB, root) runs Docker or
  bubblewrap natively — unlike PaaS (Render/Railway/Fly), which can't nest containers cleanly.
- **Lighter sandbox:** swap the Docker backend in [sandbox/runner.py](sandbox/runner.py) for a
  `bwrap` (bubblewrap) backend — same egress-proxy contract, no daemon; this is exactly what
  Claude Code uses for its own bash sandbox. For a hard kernel boundary, gVisor/Firecracker slot
  in behind the same interface.
```
