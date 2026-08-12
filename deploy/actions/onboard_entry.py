"""Entrypoint for the `onboard` GitHub Actions workflow (TASKS D.7).

Runs the SAME sandboxed resolver the local DockerAgentRunner uses - but here on the Actions
runner, which HAS Docker (Cloud Run does not, which is why cloud onboarding dispatches this
workflow). Writes `contract.json` (uploaded as an artifact the ActionsAgentRunner downloads).
If the agent drafts a new ATS adapter under providers/sources/, a later workflow step opens a PR.
"""
from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--careers-url", default="")
    a = ap.parse_args()

    def on_event(stage: str, status: str, detail: str = "") -> None:
        print(f"[{status}] {stage}: {detail}", flush=True)

    # Deterministic-first ON THE RUNNER. Unlike the lean cloud API image, the Actions runner has a
    # headless browser (installed by the workflow), so JS-only careers sites — Algolia InstantSearch
    # and friends, whose board creds exist only at runtime — resolve here cheaply with NO LLM. Only
    # if this misses do we spin up the sandboxed agent for the genuinely-novel tail.
    from resumaker.ingestion import onboard as det  # noqa: PLC0415

    res = det.resolve(a.name, careers_url=a.careers_url or None)
    if res.resolved and res.boards:
        b = res.boards[0]
        on_event("deterministic", "done", f"{b.source}:{b.token} via {res.method}")
        contract = {"status": "resolved",
                    "board": {"source": b.source, "token": b.token, "extra": b.extra},
                    "evidence": {"method": res.method}, "cost_usd": 0.0, "turns": 0}
    else:
        on_event("deterministic", "skip", "no board on the runner; escalating to sandboxed agent")
        # Force the local Docker sandbox (never re-dispatch Actions from inside Actions).
        os.environ["RESUMAKER_ONBOARD_AGENT_ENABLED"] = "true"
        os.environ["RESUMAKER_ONBOARD_RUNNER"] = "docker"
        from resumaker.onboarding.agent_runner import DockerAgentRunner  # noqa: PLC0415
        contract = DockerAgentRunner().resolve(
            a.name, a.careers_url or None, run_id=a.run_id, on_event=on_event)

    with open("contract.json", "w") as fh:
        json.dump(contract, fh, indent=2)
    print("wrote contract.json:", contract.get("status"))


if __name__ == "__main__":
    main()
