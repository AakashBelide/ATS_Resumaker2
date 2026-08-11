"""Host-side driver for the sandboxed resolver agent.

Runs the Claude CLI *inside* the locked resolver container (tools + hook + egress allow-list),
parses its final JSON contract, and returns it. The OAuth token is read from a gitignored file
(or the env) and forwarded to the container by NAME only, so it never appears on a command line,
in `ps`, or in any log.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

POC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC_DIR / "sandbox"))
import runner  # noqa: E402

SYSTEM_PROMPT = (POC_DIR / "agent" / "system_prompt.md").read_text()
TOKEN_FILE = POC_DIR / ".secrets" / "claude_oauth_token"


def _registrable(host: str) -> str:
    """Company registrable domain (naive eTLD+1) — good enough to scope egress to the target's
    own infrastructure. e.g. jobs.navyfederal.org -> navyfederal.org."""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _supported_platforms() -> str:
    """The platforms the system can ingest AND the exact BoardRef `extra` keys each one needs —
    both derived by INTROSPECTING the real adapters (`list_postings` keyword-only params). So the
    agent always targets the real supported set with the correct param schema, and nothing is
    hand-maintained per platform or per company."""
    try:
        import inspect  # noqa: PLC0415
        from resumaker.providers.sources import available_sources, get_source  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - POC may run without the package importable
        return ("- greenhouse / lever / ashby (extra keys: none; token = board slug)\n"
                "- workday (extra keys: host, site)\n- oracle_cloud (extra keys: host, site)\n"
                "- radancy (extra keys: origin, lang)")
    lines = []
    for name in sorted(available_sources()):
        try:
            sig = inspect.signature(get_source(name).list_postings)
            keys = [p.name for p in sig.parameters.values() if p.kind == p.KEYWORD_ONLY]
        except Exception:  # noqa: BLE001
            keys = []
        lines.append(f"- {name}" + (f" (extra keys: {', '.join(keys)})" if keys
                                     else " (extra keys: none)"))
    return "\n".join(lines)


class AuthMissing(RuntimeError):
    pass


def _token() -> str:
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not tok and TOKEN_FILE.exists():
        tok = TOKEN_FILE.read_text().strip()
    if not tok:
        raise AuthMissing(
            "No Claude auth. Run `claude setup-token` on the host and save the token to "
            f"{TOKEN_FILE} (gitignored), or export CLAUDE_CODE_OAUTH_TOKEN.")
    return tok


def _parse_cli(cli_stdout: str) -> tuple[str, dict]:
    """claude --output-format json -> (final_text, metrics). metrics carries the usage caps we
    track: cost_usd, turns, duration_s."""
    metrics = {"cost_usd": None, "turns": None, "duration_s": None}
    try:
        obj = json.loads(cli_stdout)
    except json.JSONDecodeError:
        return cli_stdout, metrics
    if isinstance(obj, dict):
        metrics["cost_usd"] = obj.get("total_cost_usd")
        metrics["turns"] = obj.get("num_turns")
        if obj.get("duration_ms") is not None:
            metrics["duration_s"] = round(obj["duration_ms"] / 1000, 1)
        return obj.get("result", ""), metrics
    return cli_stdout, metrics


def _extract_contract(text: str) -> dict:
    """Pull the JSON contract out of the agent's final message (possibly fenced)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"(\{.*\})", text, re.S)  # last-resort: first {...} span
        if m:
            text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"status": "error", "note": "agent did not return valid JSON",
                "raw": text[:500]}


def resolve_via_agent(name: str, careers_url: str | None = None, *,
                      model: str = "sonnet", project: str = "onboard-sandbox",
                      max_turns: int = 20, time_limit: int = 600) -> dict:
    """Run the sandboxed agent to resolve `name` -> board ref. Caps: `max_turns` bounds the
    agent's tool-call loop (usage cap); `time_limit` is the wall-clock auto-kill. Returns the
    parsed contract plus `_meta` (returncode, cost/turns, proxy decisions)."""
    token = _token()
    extra_allow = ""
    if careers_url:
        host = urlsplit(careers_url if "://" in careers_url else "https://" + careers_url).hostname
        # Open egress to the company's WHOLE domain (not just the exact host) so the agent can
        # get its hands dirty on the company's own careers/API infra. Still deny-by-default
        # everywhere else, so exfiltration to an attacker host stays blocked.
        extra_allow = ("." + _registrable(host)) if host else ""

    system = SYSTEM_PROMPT + "\n\n# Supported platforms (return exactly one as `source`)\n" + \
        _supported_platforms()
    task = f"Company name: {name}\nCareers URL: {careers_url or '(none provided)'}"
    argv = [
        "claude", "-p", task,
        "--output-format", "json",
        "--model", model,
        "--max-turns", str(max_turns),      # usage cap: bounds the tool-call loop
        "--dangerously-skip-permissions",   # the sandbox is the boundary, not the prompt
        "--settings", "/opt/agent/claude-settings.json",
        "--disallowedTools", "WebFetch,WebSearch",   # force our auditable fetch tool
        "--append-system-prompt", system,
    ]
    res = runner.run(argv, service="resolver", project=project, extra_allow=extra_allow,
                     forward_env=["CLAUDE_CODE_OAUTH_TOKEN"],
                     env_extra={"CLAUDE_CODE_OAUTH_TOKEN": token},
                     timeout=time_limit)
    decisions = [ln for ln in res.proxy_log.splitlines() if ln.startswith(("ALLOW", "DENY"))]

    if res.timed_out:
        contract: dict = {"status": "killed", "reason": f"time limit {time_limit}s exceeded"}
    else:
        text, metrics = _parse_cli(res.stdout)
        contract = _extract_contract(text)
        contract.setdefault("_metrics", metrics)

    metrics = contract.pop("_metrics", {"cost_usd": None, "turns": None, "duration_s": None})
    contract["_meta"] = {
        "returncode": res.returncode,
        "timed_out": res.timed_out,
        "cost_usd": metrics.get("cost_usd"),
        "turns": metrics.get("turns"),
        "duration_s": metrics.get("duration_s"),
        "proxy_decisions": decisions[-30:],
        "denied_hosts": sorted({ln.split(" ", 1)[1] for ln in decisions if ln.startswith("DENY")}),
        "stderr_tail": res.stderr[-400:],
    }
    return contract


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--careers-url", default=None)
    a = ap.parse_args()
    print(json.dumps(resolve_via_agent(a.name, a.careers_url), indent=2))
