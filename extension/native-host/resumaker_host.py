#!/usr/bin/env python3
"""Native messaging host for the ATS Resumaker browser extension.

Chrome/Edge/Brave speak the "native messaging" protocol over stdio: a 4-byte little-endian
length prefix followed by a JSON message. The extension sends {action:"track", url, no_match}
and this host runs the project's CLI (`apps.cli track add`) to add the job to the tracker -
so tracking works even when the FastAPI server is NOT running (the extension's CLI-first path).
It replies with a 4-byte length + JSON {ok, output|error}.

Only the Python stdlib is used here; the actual work runs in the project venv via subprocess.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

# extension/native-host/resumaker_host.py -> project root is two parents up.
ROOT = Path(__file__).resolve().parents[2]
VENV_PY = ROOT / ".venv" / "bin" / "python"


def _read_message() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("<I", raw)
    payload = sys.stdin.buffer.read(length)
    return json.loads(payload.decode("utf-8"))


def _send(obj: dict) -> None:
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def main() -> None:
    try:
        msg = _read_message()
    except Exception as e:  # noqa: BLE001 - always reply with a structured error
        _send({"ok": False, "error": f"bad message: {e}"})
        return
    if not msg:
        return

    url = str(msg.get("url") or "").strip()
    if not url:
        _send({"ok": False, "error": "no url provided"})
        return

    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    cmd = [py, "-m", "apps.cli", "track", "add", "--url", url]
    if msg.get("no_match", True):        # default: instant add, no synchronous match
        cmd.append("--no-match")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=200)
    except Exception as e:  # noqa: BLE001
        _send({"ok": False, "error": f"launch failed: {e}"})
        return
    if proc.returncode == 0:
        _send({"ok": True, "output": (proc.stdout or "").strip()[-600:]})
    else:
        _send({"ok": False, "error": (proc.stderr or proc.stdout or "").strip()[-600:]})


if __name__ == "__main__":
    main()
