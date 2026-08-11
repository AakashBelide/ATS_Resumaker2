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
                on_event: OnEvent) -> dict: ...

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

    def resolve(self, name: str, careers_url: str | None, *, run_id: str, on_event: OnEvent) -> dict:
        s = get_settings()
        on_event("agent", "start", "sandboxed Claude resolver")
        c = self._resolve_via_agent(
            name, careers_url, project=f"onboard-{run_id}",
            max_turns=s.onboard_max_turns, time_limit=s.onboard_time_limit_s)
        meta = c.get("_meta", {}) or {}
        return {
            "status": c.get("status", "unresolved"),
            "board": c.get("board"),
            "evidence": c.get("evidence") or {},
            "question": c.get("question", ""),
            "note": c.get("note", "") or c.get("reason", ""),
            "tried": c.get("tried", []),
            "cost_usd": float(meta.get("cost_usd") or 0.0),
            "turns": int(meta.get("turns") or 0),
        }

    def stop(self, run_id: str) -> None:
        try:
            self._runner.kill(f"onboard-{run_id}")
        except Exception as e:  # noqa: BLE001
            _log.warning("stop/kill failed for %s: %s", run_id, e)


def get_agent_runner() -> AgentRunner:
    """Return the configured agent runner (Null unless the agent is enabled + available)."""
    if not get_settings().onboard_agent_enabled:
        return NullAgentRunner()
    try:
        return DockerAgentRunner()
    except Exception as e:  # noqa: BLE001
        _log.warning("agent enabled but runner unavailable: %s", e)
        return NullAgentRunner(note=f"agent enabled but runner unavailable: {e}")
