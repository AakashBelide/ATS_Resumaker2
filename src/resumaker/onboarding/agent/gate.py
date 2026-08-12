"""Validation gate for LLM-drafted ATS adapters.

Model-authored adapter code NEVER lands unchecked. Layers:
  1. static_check (here): AST allow-list — only safe imports, no dangerous builtins/dunder access,
     and it must actually define a SourceAdapter (a class with a `source` attr + `list_postings`).
  2. live validation (validate_adapter in the runner): run the vetted adapter INSIDE the locked
     sandbox against the real board and require > 0 well-formed postings.
  3. human review: only after both pass is the file written under providers/sources/ and a PR
     opened — a person approves before it can merge/run in prod.

This module is import-safe and dependency-free (stdlib `ast` only), so the gate itself never runs
the code it inspects.
"""
from __future__ import annotations

import ast
import json
import os
import tempfile
from pathlib import Path

# Import ROOTS the adapter may use (job-board adapters need only these). `resumaker` is further
# restricted to the sources package below.
_ALLOWED_ROOTS = {
    "resumaker", "httpx", "re", "json", "dataclasses", "typing",
    "urllib", "__future__", "html", "contextlib", "datetime",
}
_BANNED_ROOTS = {
    "os", "sys", "subprocess", "socket", "importlib", "shutil", "pathlib", "ctypes",
    "multiprocessing", "threading", "asyncio", "builtins", "pickle", "marshal", "code",
    "pty", "signal", "resource", "fcntl", "mmap", "tempfile", "glob", "requests", "urllib3",
}
_BANNED_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "input", "breakpoint", "memoryview", "exit", "quit",
}


def _import_ok(module: str) -> bool:
    root = (module or "").split(".")[0]
    if root in _BANNED_ROOTS:
        return False
    if root == "resumaker":
        return module.startswith("resumaker.providers.sources")
    return root in _ALLOWED_ROOTS


def _defines_adapter(tree: ast.AST) -> bool:
    """True if some class has a `source` assignment/annotation AND a `list_postings` method."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        has_source = has_list = False
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "list_postings":
                has_list = True
            if isinstance(item, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "source" for t in item.targets):
                has_source = True
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) \
                    and item.target.id == "source":
                has_source = True
        if has_source and has_list:
            return True
    return False


def static_check(code: str) -> tuple[bool, list[str]]:
    """Static AST gate. Returns (ok, errors). ok=True means the code only touches the allow-listed
    surface and is shaped like a SourceAdapter; it does NOT mean the adapter actually works — that
    is the live sandbox run's job."""
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"syntax error: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _import_ok(a.name):
                    errors.append(f"disallowed import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level or not _import_ok(node.module or ""):
                errors.append(f"disallowed import-from: {'.' * node.level}{node.module or ''}")
        elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            errors.append(f"banned builtin: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") \
                and node.attr.endswith("__"):
            errors.append(f"dunder attribute access: {node.attr}")

    if not _defines_adapter(tree):
        errors.append("no SourceAdapter class (needs a `source` attribute + `list_postings` method)")

    # de-dupe, preserve order
    return (not errors), list(dict.fromkeys(errors))


# The shim runs INSIDE the locked sandbox. It stubs the tiny adapter API surface (PostingStub +
# polite_get/polite_post + UA), loads the drafted adapter, runs list_postings against the real
# board, and prints one JSON result to stdout. Trusted code (ours), so it may import freely — the
# AST gate constrains the *adapter*, not this shim.
_SHIM = r'''
import json, sys, types
from dataclasses import dataclass, field
import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

@dataclass
class PostingStub:
    source: str
    external_id: str
    url: str = ""
    title: str = ""
    location: str = ""
    updated_at: str = ""
    comp: str = ""
    extra: dict = field(default_factory=dict)

def polite_get(url, headers, *, timeout=20.0, attempts=3):
    return httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)

def polite_post(url, headers, *, json=None, content=None, timeout=20.0, attempts=3):
    return httpx.post(url, headers=headers, json=json, content=content, timeout=timeout,
                      follow_redirects=True)

def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m

for _n in ("resumaker", "resumaker.providers", "resumaker.providers.sources"):
    _mod(_n)
_mod("resumaker.providers.sources.base", PostingStub=PostingStub)
_mod("resumaker.providers.sources.http", polite_get=polite_get, polite_post=polite_post)
_mod("resumaker.providers.sources.ua", UA=UA)

def out(d):
    print(json.dumps(d)); sys.exit(0)

ns = {}
try:
    exec(compile(open("/gate/adapter.py").read(), "adapter.py", "exec"), ns)
except Exception as e:  # noqa: BLE001
    out({"ok": False, "stage": "load", "error": f"{type(e).__name__}: {e}"[:300]})

cls = next((v for v in ns.values()
            if isinstance(v, type) and hasattr(v, "source") and hasattr(v, "list_postings")), None)
if cls is None:
    out({"ok": False, "stage": "load", "error": "no adapter class found"})

board = json.load(open("/gate/board.json"))
extra = {k: str(v) for k, v in (board.get("extra") or {}).items()}
try:
    stubs = cls().list_postings(board.get("token", ""), **extra)
except Exception as e:  # noqa: BLE001
    out({"ok": False, "stage": "run", "error": f"{type(e).__name__}: {e}"[:300]})

n = len(stubs)
well = sum(1 for s in stubs if getattr(s, "external_id", "") and getattr(s, "title", ""))
sample = [{"external_id": str(getattr(s, "external_id", ""))[:40],
           "title": str(getattr(s, "title", ""))[:60],
           "location": str(getattr(s, "location", ""))[:40]} for s in stubs[:4]]
out({"ok": n > 0 and well > 0, "stage": "run", "count": n, "well_formed": well,
     "source": getattr(cls, "source", ""), "sample": sample})
'''


def validate_adapter(code: str, board: dict, *, allow_hosts: list[str] | None = None,
                     project: str = "gate", timeout: int = 120) -> dict:
    """Full gate: static AST check, then RUN the adapter inside the locked sandbox against the real
    board (egress limited to `allow_hosts` + the board's own host) and require >0 well-formed
    postings. `board` = {"source","token","extra"}. Returns
    {ok, stage, count?, well_formed?, sample?, errors?/error?}."""
    ok, errs = static_check(code)
    if not ok:
        return {"ok": False, "stage": "static", "errors": errs}

    from resumaker.onboarding.sandbox import runner  # noqa: PLC0415

    hosts = list(allow_hosts or [])
    if (h := (board.get("extra") or {}).get("host")):
        hosts.append(str(h))
    extra_allow = ",".join(h for h in dict.fromkeys(hosts) if h)

    with tempfile.TemporaryDirectory(prefix="gate-") as td:
        d = Path(td)
        (d / "adapter.py").write_text(code)
        (d / "shim.py").write_text(_SHIM)
        (d / "board.json").write_text(json.dumps(
            {"token": board.get("token", ""), "extra": board.get("extra") or {}}))
        # The sandbox runs as non-root uid 10001; TemporaryDirectory is 0700, so on a Linux host
        # (the Actions runner) that user can't read the bind-mounted /gate. Make it world-readable.
        os.chmod(td, 0o755)
        for f in ("adapter.py", "shim.py", "board.json"):
            os.chmod(d / f, 0o644)
        res = runner.run(["python3", "/gate/shim.py"], service="agent", project=project,
                         extra_allow=extra_allow, mounts=[(td, "/gate")], timeout=timeout)
    if res.timed_out:
        return {"ok": False, "stage": "run", "error": f"timed out after {timeout}s"}
    line = next((ln for ln in reversed(res.stdout.splitlines()) if ln.strip().startswith("{")), "")
    if not line:
        return {"ok": False, "stage": "run",
                "error": f"no result (rc={res.returncode}): {res.stderr[-200:]}"}
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "stage": "run", "error": f"unparseable result: {line[:200]}"}
