"""Onboarding agent-runner seam.

Deterministic-first resolution ($0, no sandbox) always runs in the service; when it misses and the
sandboxed agent is enabled (`RESUMAKER_ONBOARD_AGENT_ENABLED` + Docker + a Claude token), this
returns a runner that resolves the hard tail inside a locked sandbox. Default = `NullAgentRunner`
(deterministic-only), so onboarding works with zero extra infra.

`DockerAgentRunner` uses the local Docker sandbox (`resumaker.onboarding.sandbox`). A cloud
(GitHub-Actions) runner implementing the same interface is the deploy-time counterpart (TASKS D.7).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from resumaker.config import get_settings
from resumaker.observability.logging import get_logger

_log = get_logger("resumaker.onboarding.agent")

# on_event(stage, status, detail) — progress callback the runner may call during a resolve.
OnEvent = Callable[[str, str, str], None]


class AgentRunner(Protocol):
    def resolve(self, name: str, careers_url: str | None, *, run_id: str,
                on_event: OnEvent, fingerprint: dict | None = None) -> dict: ...

    def stop(self, run_id: str) -> None: ...


class NullAgentRunner:
    """No sandbox. Reports the hard tail as unresolved with a clear, actionable note."""

    def __init__(self, note: str = ""):
        self._note = note or (
            "agent fallback disabled (set RESUMAKER_ONBOARD_AGENT_ENABLED=true, with Docker + a "
            "Claude token) — deterministic-only. Try adding the company's careers URL.")

    def resolve(self, name: str, careers_url: str | None, *, run_id: str, on_event: OnEvent) -> dict:
        return {"status": "unresolved", "note": self._note, "cost_usd": 0.0, "turns": 0}

    def stop(self, run_id: str) -> None:
        return None


class DockerAgentRunner:
    """Runs the sandboxed resolver via the local Docker sandbox (`resumaker.onboarding.sandbox`)."""

    def __init__(self) -> None:
        from resumaker.onboarding.agent import resolve as agent_resolve  # noqa: PLC0415
        from resumaker.onboarding.sandbox import runner as sandbox_runner  # noqa: PLC0415
        self._resolve_via_agent = agent_resolve.resolve_via_agent
        self._runner = sandbox_runner

    def resolve(self, name: str, careers_url: str | None, *, run_id: str, on_event: OnEvent,
                fingerprint: dict | None = None) -> dict:
        s = get_settings()
        on_event("agent", "start", "sandboxed Claude resolver")
        c = self._resolve_via_agent(
            name, careers_url, project=f"onboard-{run_id}",
            max_turns=s.onboard_max_turns, time_limit=s.onboard_time_limit_s,
            fingerprint=fingerprint)
        meta = c.get("_meta", {}) or {}
        # Surface the sandbox diagnostics when the agent didn't cleanly resolve — otherwise the
        # returncode/stderr/raw output are lost (only the top-level contract is uploaded), leaving
        # failures like "did not return valid JSON" impossible to root-cause from the logs.
        if c.get("status") not in ("resolved", "needs_input"):
            tail = " ".join((meta.get("stderr_tail") or "").split())[-300:]
            raw = " ".join((c.get("raw") or "").split())[:200]
            on_event("agent", "progress",
                     f"diag rc={meta.get('returncode')} timed_out={meta.get('timed_out')} "
                     f"denied={meta.get('denied_hosts')} stderr={tail!r} raw={raw!r}")
        return {
            "status": c.get("status", "unresolved"),
            "board": c.get("board"),
            "evidence": c.get("evidence") or {},
            "question": c.get("question", ""),
            "note": c.get("note", "") or c.get("reason", ""),
            "tried": c.get("tried", []),
            "adapter_code": c.get("adapter_code"),      # present when the agent drafted an adapter
            "adapter_name": c.get("adapter_name", ""),
            "cost_usd": float(meta.get("cost_usd") or 0.0),
            "turns": int(meta.get("turns") or 0),
        }

    def stop(self, run_id: str) -> None:
        try:
            self._runner.kill(f"onboard-{run_id}")
        except Exception as e:  # noqa: BLE001
            _log.warning("stop/kill failed for %s: %s", run_id, e)


class ActionsAgentRunner:
    """Runs the sandboxed resolver on GitHub Actions - the cloud counterpart of DockerAgentRunner
    (Cloud Run can't nest Docker, but an Actions runner has Docker). Dispatch -> poll -> download
    the result artifact, all synchronous, so it drops into the same `resolve()` seam. The workflow
    (`.github/workflows/onboard.yml`) runs the SAME sandbox and, if the agent drafts a new adapter,
    opens a PR. Needs `github_repo` + a `github_token` (PAT with actions:write, contents:write)."""

    _API = "https://api.github.com"

    def __init__(self) -> None:
        s = get_settings()
        if not (s.github_repo and s.github_token):
            raise RuntimeError("onboard_runner=actions needs github_repo + RESUMAKER_GITHUB_TOKEN")
        self._repo = s.github_repo
        self._workflow = s.github_workflow
        self._ref = "main"
        self._poll_s = 10
        self._deadline_s = s.onboard_time_limit_s
        self._runs: dict[str, int] = {}   # run_id -> GitHub Actions run id (for stop())
        import httpx  # noqa: PLC0415
        self._http = httpx.Client(
            base_url=self._API, timeout=30,
            headers={"Authorization": f"Bearer {s.github_token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"})

    def resolve(self, name: str, careers_url: str | None, *, run_id: str, on_event: OnEvent,
                fingerprint: dict | None = None) -> dict:
        # `fingerprint` is ignored here: the Actions runner does its own headless fingerprint (it
        # has a browser; the lean cloud API that dispatches this does not), inside onboard_entry.
        import time  # noqa: PLC0415
        on_event("agent", "start", "dispatching GitHub Actions resolve")
        dispatched_at = time.time()
        # 1) dispatch (204, no run id returned) - the workflow sets run-name=onboard-<run_id>.
        self._http.post(
            f"/repos/{self._repo}/actions/workflows/{self._workflow}/dispatches",
            json={"ref": self._ref, "inputs": {
                "run_id": run_id, "name": name, "careers_url": careers_url or ""}},
        ).raise_for_status()
        # 2) find the run by its run-name, then 3) wait for completion.
        gh_run = self._await_run(run_id, dispatched_at, on_event)
        if gh_run is None:
            return {"status": "unresolved", "note": "Actions run not found/timed out",
                    "cost_usd": 0.0, "turns": 0}
        if gh_run.get("conclusion") != "success":
            return {"status": "unresolved",
                    "note": f"Actions run {gh_run.get('conclusion')}: {gh_run.get('html_url', '')}",
                    "cost_usd": 0.0, "turns": 0}
        # 4) download the contract artifact the workflow uploaded.
        contract = self._fetch_contract(int(gh_run["id"]), run_id)
        return contract or {"status": "unresolved", "note": "no contract artifact",
                            "cost_usd": 0.0, "turns": 0}

    def _await_run(self, run_id: str, since: float, on_event: OnEvent) -> dict | None:
        import time  # noqa: PLC0415
        want = f"onboard-{run_id}"
        gh_id: int | None = None
        while time.time() - since < self._deadline_s:
            time.sleep(self._poll_s)
            runs = self._http.get(
                f"/repos/{self._repo}/actions/runs",
                params={"event": "workflow_dispatch", "per_page": 30},
            ).json().get("workflow_runs", [])
            match = next((r for r in runs if r.get("name") == want), None)
            if match is None:
                continue
            gh_id = int(match["id"])
            self._runs[run_id] = gh_id
            if match.get("status") == "completed":
                on_event("agent", "done", f"Actions {match.get('conclusion')}")
                return match
            on_event("agent", "progress", f"Actions {match.get('status')}")
        _ = gh_id
        return None

    def _fetch_contract(self, gh_run_id: int, run_id: str) -> dict | None:
        import io  # noqa: PLC0415
        import json  # noqa: PLC0415
        import zipfile  # noqa: PLC0415
        arts = self._http.get(
            f"/repos/{self._repo}/actions/runs/{gh_run_id}/artifacts").json().get("artifacts", [])
        art = next((a for a in arts if a.get("name") == f"contract-{run_id}"), None)
        if art is None:
            return None
        zip_bytes = self._http.get(art["archive_download_url"], follow_redirects=True).content
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z, z.open("contract.json") as fh:
            return json.load(fh)

    def stop(self, run_id: str) -> None:
        gh_id = self._runs.get(run_id)
        if gh_id is None:
            return
        try:
            self._http.post(f"/repos/{self._repo}/actions/runs/{gh_id}/cancel")
        except Exception as e:  # noqa: BLE001
            _log.warning("actions cancel failed for %s: %s", run_id, e)


def get_agent_runner() -> AgentRunner:
    """Return the configured agent runner (Null unless the agent is enabled + available). When
    enabled, `onboard_runner` picks the sandbox host: `docker` (local) or `actions` (cloud)."""
    if not get_settings().onboard_agent_enabled:
        return NullAgentRunner()
    runner = get_settings().onboard_runner
    try:
        return ActionsAgentRunner() if runner == "actions" else DockerAgentRunner()
    except Exception as e:  # noqa: BLE001
        _log.warning("agent enabled but runner unavailable: %s", e)
        return NullAgentRunner(note=f"agent enabled but runner unavailable: {e}")
