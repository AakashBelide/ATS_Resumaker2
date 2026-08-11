"""Adapter AUTHOR — the sandboxed agent that writes a NEW source adapter for a platform that has
no adapter yet. It explores the platform's public API, captures a fixture, and drafts the adapter
+ a unit test, emitting them as text artifacts (no repo access). Artifacts are saved to a
gitignored drafts dir for the gate + human review; they NEVER auto-integrate.

  python -m pocs.agentic_onboard.adapter_writer.author "SAP" \
      --careers-url https://jobs.sap.com/ --source successfactors \
      --allow .successfactors.eu,.successfactors.com,.sap.com
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from resumaker.onboarding.agent import resolve as agent_resolve  # reuse token + CLI-output parsing
from resumaker.onboarding.sandbox import runner

POC_DIR = Path(__file__).resolve().parents[1]

AUTHOR_PROMPT = (Path(__file__).resolve().parent / "author_prompt.md").read_text()
DRAFTS_DIR = POC_DIR / "adapter_writer" / "drafts"


def author_adapter(name: str, careers_url: str, source: str, allow: str, *,
                   model: str = "sonnet", max_turns: int = 80, time_limit: int = 2700) -> dict:
    token = agent_resolve._token()
    out = DRAFTS_DIR / source
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o777)   # the sandbox writes as uid 10001; let it emit artifacts here

    task = (f"Company: {name}\nCareers URL: {careers_url}\nPlatform id (use as `source`): "
            f"{source}\nWrite the adapter, fixture, and test for this platform into /out.")
    argv = [
        "claude", "-p", task,
        "--output-format", "json", "--model", model,
        "--max-turns", str(max_turns),
        "--dangerously-skip-permissions",
        "--settings", "/opt/agent/claude-settings.json",
        "--disallowedTools", "WebFetch,WebSearch",
        "--append-system-prompt", AUTHOR_PROMPT,
    ]
    res = runner.run(argv, service="resolver", project=f"authoring-{source}",
                     extra_allow=allow, forward_env=["CLAUDE_CODE_OAUTH_TOKEN"],
                     env_extra={"CLAUDE_CODE_OAUTH_TOKEN": token},
                     mounts=[(str(out), "/out:rw")], timeout=time_limit)

    text, metrics = agent_resolve._parse_cli(res.stdout)
    contract = agent_resolve._extract_contract(text) if not res.timed_out else \
        {"status": "killed", "reason": f"time limit {time_limit}s exceeded"}
    # Source of truth = what actually landed in /out (captures partial work even on timeout).
    written = sorted(p.name for p in out.iterdir() if p.is_file())
    contract["_written"] = written
    contract["_meta"] = {"cost_usd": metrics.get("cost_usd"), "turns": metrics.get("turns"),
                         "timed_out": res.timed_out, "out_dir": str(out),
                         "denied_hosts": sorted({ln.split(" ", 1)[1] for ln in res.proxy_log.splitlines()
                                                 if ln.startswith("DENY")})}
    if written and contract.get("status") not in ("drafted",):
        contract.setdefault("status", "partial")
        if contract.get("status") in ("error", "killed"):
            contract["status"] = "partial"
    return contract


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--careers-url", required=True)
    ap.add_argument("--source", required=True, help="platform id, e.g. successfactors")
    ap.add_argument("--allow", required=True, help="comma-sep egress hosts for the new platform")
    a = ap.parse_args()
    out = author_adapter(a.name, a.careers_url, a.source, a.allow)
    print(json.dumps(out, indent=2))
    return 0 if out.get("status") in ("drafted", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
