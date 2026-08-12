"""Entrypoint for the `onboard` GitHub Actions workflow (TASKS D.7).

Runs the SAME sandboxed resolver the local DockerAgentRunner uses - but here on the Actions
runner, which HAS Docker (Cloud Run does not, which is why cloud onboarding dispatches this
workflow). Writes `contract.json` (uploaded as an artifact the ActionsAgentRunner downloads).
If the agent drafts a new ATS adapter under providers/sources/, a later workflow step opens a PR.
"""
from __future__ import annotations

import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--careers-url", default="")
    a = ap.parse_args()

    def on_event(stage: str, status: str, detail: str = "") -> None:
        print(f"[{status}] {stage}: {detail}", flush=True)

    # The runner has a headless browser + Docker (the lean cloud API has neither), so the full flow
    # lives here: deterministic resolve -> fingerprint -> sandboxed agent (map OR draft a new
    # adapter) -> gate + write + register. A drafted adapter lands under providers/sources/ for the
    # workflow's next step to open a PR.
    from resumaker.onboarding.drafting import orchestrate  # noqa: PLC0415

    contract = orchestrate(a.name, a.careers_url or None, run_id=a.run_id, on_event=on_event)

    with open("contract.json", "w") as fh:
        json.dump(contract, fh, indent=2)
    print("wrote contract.json:", contract.get("status"))


if __name__ == "__main__":
    main()
