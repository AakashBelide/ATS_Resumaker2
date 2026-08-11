#!/usr/bin/env python3
"""PreToolUse hook — in-box policy gate (defense-in-depth).

The container is already the security wall (non-root, read-only, no secrets, egress
allow-list). This hook is the belt-and-suspenders layer INSIDE the box: it inspects every
tool call before it runs and blocks (exit code 2, reason on stderr) anything off-policy —
credential-path access, raw network tools, destructive commands, writes outside /work.
Every call is logged to /tmp/hook-audit.log for the transcript.

Claude Code invokes this per PreToolUse with the tool call as JSON on stdin.
Exit 0 = allow, exit 2 = block (stderr text shown to the model as the denial reason).
"""
from __future__ import annotations

import json
import re
import sys

CRED = re.compile(r"(\.env\b|/\.claude|/\.aws|/\.ssh|id_rsa|credentials|"
                  r"CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY|/etc/shadow)", re.I)
RAW_NET = re.compile(r"\b(nc|ncat|netcat|telnet|ssh|scp|sftp|ftp)\b")
DESTRUCTIVE = re.compile(r"\brm\s+-rf\s+/(?!work|tmp)|\bmkfs|\bdd\s+if=|:\(\)\s*\{|\bshutdown\b|\breboot\b")
WRITE_OUTSIDE = re.compile(r">>?\s*/(?!work|tmp|dev/null)")


def block(reason: str) -> None:
    print(f"[hook] DENY: {reason}", file=sys.stderr)
    try:
        with open("/tmp/hook-audit.log", "a") as f:
            f.write(f"DENY {reason}\n")
    except OSError:
        pass
    sys.exit(2)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # never break the run on a malformed hook payload
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}

    for p in (ti.get("file_path", ""), ti.get("path", "")):
        if p and CRED.search(str(p)):
            block(f"credential/secret path access blocked: {p}")

    cmd = ti.get("command", "") if tool == "Bash" else ""
    if cmd:
        if CRED.search(cmd):
            block("command references a credential/secret path")
        if RAW_NET.search(cmd):
            block("raw network tool blocked (use the fetch/ats_probe tools)")
        if DESTRUCTIVE.search(cmd):
            block("destructive command blocked")
        if WRITE_OUTSIDE.search(cmd):
            block("write outside /work blocked (rootfs is read-only anyway)")

    try:
        with open("/tmp/hook-audit.log", "a") as f:
            f.write(f"ALLOW {tool}: {str(ti)[:160]}\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
