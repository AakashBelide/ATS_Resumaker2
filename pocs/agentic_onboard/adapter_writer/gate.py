"""Adapter GATE — automated checks that run BEFORE a human review, so the human sees a
scanned, tested, diff-minimal artifact rather than being the sole barrier.

  1. STATIC AST scan (host-side, no execution): import allow-list + ban dangerous constructs
     (os/sys/subprocess/socket/importlib/eval/exec/compile/__import__/open/dunder escapes).
  2. OFFLINE fixture test (in the sandbox): the draft's own test parses the captured fixture.
  3. LIVE check (in the sandbox, egress allow-listed): the adapter hits the real platform API
     and must return >= 1 posting.

Untrusted generated code executes ONLY inside the locked sandbox. Static scan is host-side but
never executes the code.

  python -m pocs.agentic_onboard.adapter_writer.gate personio \
      --token personio --extra '{"tld":"de"}' --allow .personio.de,.personio.com
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

POC_DIR = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
DRAFTS = HERE / "drafts"
SHIM = HERE / "shim"
sys.path.insert(0, str(POC_DIR / "sandbox"))
import runner  # noqa: E402

ALLOWED_IMPORT_ROOTS = {
    "__future__", "re", "json", "html", "dataclasses", "typing", "urllib", "pathlib",
    "collections", "datetime", "math", "resumaker",
}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "open", "input",
                "globals", "locals", "vars", "getattr", "setattr", "delattr"}
BANNED_ATTRS = {"__subclasses__", "__globals__", "__bases__", "__mro__", "__builtins__",
                "__import__", "__class__", "__dict__", "__code__"}


def static_scan(source: str) -> list[str]:
    """Return a list of violations (empty = clean). Never executes the code."""
    out: list[str] = []
    allowed = ALLOWED_IMPORT_ROOTS | {source, f"test_{source}"}
    for py in sorted((DRAFTS / source).glob("*.py")):
        try:
            tree = ast.parse(py.read_text(), filename=py.name)
        except SyntaxError as e:
            out.append(f"{py.name}: syntax error: {e}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] not in allowed:
                        out.append(f"{py.name}:{node.lineno}: banned import '{a.name}'")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root and root not in allowed:
                    out.append(f"{py.name}:{node.lineno}: banned import from '{node.module}'")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in BANNED_CALLS:
                    out.append(f"{py.name}:{node.lineno}: banned call '{node.func.id}()'")
            elif isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRS:
                out.append(f"{py.name}:{node.lineno}: banned attribute '.{node.attr}'")
    return out


def _sandbox(source: str, argv_tail: list[str], allow: str) -> runner.SandboxResult:
    draft = DRAFTS / source
    mounts = [(str(SHIM), "/shim:ro"), (str(draft), "/draft:ro"),
              (str(HERE / "run_gate.py"), "/harness/run_gate.py:ro")]
    cmd = ["python3", "/harness/run_gate.py", source, *argv_tail]
    return runner.run(cmd, service="agent", project=f"gate-{source}",
                      extra_allow=allow, mounts=mounts, timeout=180)


def gate(source: str, token: str, extra: dict, allow: str) -> dict:
    print(f"=== GATE: {source} ===")
    violations = static_scan(source)
    print("\n[1] static AST scan (import allow-list + banned constructs)")
    if violations:
        for v in violations:
            print(f"    VIOLATION {v}")
    print(f"    -> {'FAIL' if violations else 'PASS'}")

    print("\n[2] offline fixture test (sandboxed, no network)")
    r_off = _sandbox(source, ["offline"], allow)
    off_ok = "FIXTURE_TEST_PASS" in r_off.stdout
    print("    " + (r_off.stdout.strip() or r_off.stderr.strip()[-300:]))
    print(f"    -> {'PASS' if off_ok else 'FAIL'}")

    print("\n[3] live check (sandboxed, egress allow-listed)")
    board = json.dumps({"token": token, "extra": extra})
    r_live = _sandbox(source, ["live", board], allow)
    live_count = 0
    for ln in r_live.stdout.splitlines():
        if ln.startswith("LIVE_COUNT"):
            live_count = int(ln.split()[1])
    live_ok = live_count > 0
    print("    " + (r_live.stdout.strip() or r_live.stderr.strip()[-300:]))
    decisions = [ln for ln in r_live.proxy_log.splitlines() if ln.startswith(("ALLOW", "DENY"))]
    print(f"    egress: {sorted(set(decisions))}")
    print(f"    -> {'PASS' if live_ok else 'FAIL'} ({live_count} postings)")

    overall = (not violations) and off_ok and live_ok
    print(f"\n=== {'ALL GATES PASS — ready for human review' if overall else 'GATE FAILED — back to author'} ===")
    return {"static_ok": not violations, "offline_ok": off_ok, "live_ok": live_ok,
            "live_count": live_count, "overall": overall}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--token", default="")
    ap.add_argument("--extra", default="{}", help="JSON board extra, e.g. '{\"tld\":\"de\"}'")
    ap.add_argument("--allow", default="", help="comma-sep egress hosts for the live check")
    a = ap.parse_args()
    res = gate(a.source, a.token, json.loads(a.extra), a.allow)
    return 0 if res["overall"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
