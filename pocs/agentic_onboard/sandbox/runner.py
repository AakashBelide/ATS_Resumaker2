"""Host-side sandbox runner (Docker backend).

Brings up the egress proxy, runs a one-shot command inside the locked-down container, captures
its output, and tears everything down. Pluggable seam: this Docker backend is portable (Mac dev
+ any VM); a `bwrap` backend (Linux, mirrors Claude Code's own bubblewrap+proxy sandbox) can
implement the same `run()`/`kill()` for the lightweight production path.

Control layer (per the owner's requirements):
  * each run uses its own Compose PROJECT name -> fully isolated AND killable by name, so a
    frontend "Stop" button (or a watchdog) can terminate it via `kill(project)`.
  * `timeout` is the TIME-BASED auto-kill: if the agent runs too long, we terminate + tear down.
No app source, .env, or credentials are ever mounted into the container.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import catalog

SANDBOX_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = SANDBOX_DIR / "compose.yml"
ALLOWLIST_FILE = SANDBOX_DIR / "allowlist.txt"
DEFAULT_PROJECT = "onboard-sandbox"


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    proxy_log: str          # the proxy's ALLOW/DENY decisions during the run
    timed_out: bool = False  # True if killed by the time-based limit


def _compose(project: str) -> list[str]:
    return ["docker", "compose", "-p", project, "-f", str(COMPOSE_FILE)]


def _run(cmd: list[str], timeout: int | None = None,
         env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def build(project: str = DEFAULT_PROJECT, services: list[str] | None = None,
          quiet: bool = True) -> None:
    """Build images (the resolver image is FROM onboard-sandbox:poc, so base before resolver)."""
    order = services or ["proxy", "agent", "resolver"]
    q = ["--quiet"] if quiet else []
    for svc in order:
        p = _run(_compose(project) + ["build", *q, svc], timeout=2400)
        if p.returncode != 0:
            raise RuntimeError(f"image build failed for {svc}:\n{p.stdout}\n{p.stderr}")


def down(project: str = DEFAULT_PROJECT) -> None:
    _run(_compose(project) + ["down", "-v", "--remove-orphans"], timeout=120)


def kill(project: str) -> None:
    """Hard-stop a run: kill the containers then tear down. Safe to call on an already-gone run.
    This is what a manual "Stop" button and the watchdog both call."""
    _run(_compose(project) + ["kill"], timeout=60)
    down(project)


def run(argv: list[str], *, service: str = "agent", project: str = DEFAULT_PROJECT,
        extra_allow: str = "", forward_env: list[str] | None = None,
        env_extra: dict | None = None, mounts: list[tuple[str, str]] | None = None,
        timeout: int = 300) -> SandboxResult:
    """Run `argv` inside a sandbox service (`agent` = minimal, `resolver` = full Claude agent).
    `project` scopes+names the containers so they can be killed by name. `timeout` is the
    time-based auto-kill. `forward_env` = env var NAMES forwarded via `-e NAME` (values from
    env_extra, so secrets never hit the command line). Always tears down."""
    forward_env = forward_env or []
    proc_env = {"EXTRA_ALLOW": extra_allow, **(env_extra or {})}
    timed_out = False
    catalog.write_allowlist(ALLOWLIST_FILE)  # regenerate from the source catalog (never drifts)
    try:
        up = _run(_compose(project) + ["up", "-d", "--force-recreate", "proxy"],
                  timeout=120, env_extra=proc_env)
        if up.returncode != 0:
            raise RuntimeError(f"proxy up failed:\n{up.stdout}\n{up.stderr}")

        run_cmd = _compose(project) + ["run", "--rm", "-T", "--no-deps"]
        for name in forward_env:
            run_cmd += ["-e", name]
        for host_p, cont_p in (mounts or []):  # ad-hoc mounts (author output; gate shim/draft).
            run_cmd += ["-v", f"{host_p}:{cont_p}"]
        run_cmd += [service, *argv]
        try:
            proc = _run(run_cmd, timeout=timeout, env_extra=proc_env)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            _run(_compose(project) + ["kill"], timeout=60)  # promptly stop the agent
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            rc, err = 124, f"time-based kill: exceeded {timeout}s"
        proxy_log = _run(_compose(project) + ["logs", "--no-log-prefix", "proxy"],
                         timeout=30).stdout
        return SandboxResult(rc, out, err, proxy_log, timed_out)
    finally:
        down(project)
