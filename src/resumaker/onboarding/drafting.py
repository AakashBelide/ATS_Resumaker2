"""Runner-side handling for an agent that DRAFTED a new ATS adapter.

When the agent can't map a company to an existing source but the platform is publicly fetchable,
it returns a contract carrying `adapter_code` (a new `SourceAdapter`). This module gates that code
(static AST + a live run in the locked sandbox against the real board), and on success writes it
under `providers/sources/` and registers it — so the workflow's PR step opens it for human review.
Nothing here trusts the model: the adapter must pass the gate, and a person approves the PR before
it can merge/run in prod.

Runs on the Actions runner (or locally in dev), NOT inside the agent's sandbox — it needs the repo
checkout to write files and Docker to run the gate.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from resumaker.observability.logging import get_logger
from resumaker.onboarding.agent import gate

_log = get_logger("resumaker.onboarding.drafting")

OnEvent = Callable[[str, str, str], None]


def _fp_hosts(fp: dict) -> list[str]:
    """The exact API hosts the fingerprint saw — the egress the drafted adapter is allowed to hit."""
    hosts: set[str] = set()
    for call in (fp or {}).get("api_calls", []):
        if (hn := urlsplit(call.get("url", "")).hostname):
            hosts.add(hn)
    if (ah := (fp or {}).get("algolia", {}).get("host")):
        hosts.add(ah)
    return sorted(hosts)


def orchestrate(name: str, careers_url: str | None, *, run_id: str, on_event: OnEvent,
                repo_root: str | Path | None = None) -> dict:
    """The full runner-side onboarding flow (has a browser + Docker, unlike the lean cloud API):
    deterministic resolve -> headless fingerprint -> sandboxed agent (map OR draft, given the
    fingerprint) -> gate + write + register a drafted adapter. Returns the final contract."""
    from resumaker.ingestion import onboard as det  # noqa: PLC0415
    from resumaker.ingestion.fingerprint import fingerprint as fp_fn  # noqa: PLC0415
    from resumaker.onboarding.agent_runner import DockerAgentRunner  # noqa: PLC0415

    res = det.resolve(name, careers_url=careers_url or None)
    if res.resolved and res.boards:
        b = res.boards[0]
        on_event("deterministic", "done", f"{b.source}:{b.token} via {res.method}")
        return {"status": "resolved",
                "board": {"source": b.source, "token": b.token, "extra": b.extra},
                "evidence": {"method": res.method}}
    on_event("deterministic", "skip", "no supported board; fingerprinting for the agent")

    fp: dict = {}
    if careers_url:
        on_event("fingerprint", "start", "headless capture of the careers page")
        fp = fp_fn(careers_url)
        on_event("fingerprint", "done",
                 f"api_calls={len(fp.get('api_calls', []))} algolia={'yes' if fp.get('algolia') else 'no'}")

    contract = DockerAgentRunner().resolve(name, careers_url or None, run_id=run_id,
                                           on_event=on_event, fingerprint=fp)
    if contract.get("adapter_code"):
        on_event("draft", "start", f"gating drafted adapter '{contract.get('adapter_name', '?')}'")
        # The gate runs the adapter with egress to the fingerprinted hosts PLUS the careers
        # domain (where a board API usually lives — the fingerprint misses server-rendered feeds).
        allow = _fp_hosts(fp)
        if careers_url:
            h = urlsplit(careers_url if "://" in careers_url else "https://" + careers_url).hostname
            if h:
                allow.append(h)
                parts = h.split(".")
                if len(parts) >= 2:
                    allow.append("." + ".".join(parts[-2:]))   # wildcard the registrable domain
        contract = process_draft(contract, allow_hosts=allow, repo_root=repo_root)
        on_event("draft", "done" if contract.get("status") == "drafted" else "error",
                 contract.get("note", "")[:120])
    return contract


def _repo_root() -> Path:
    # .../src/resumaker/onboarding/drafting.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def _safe_name(raw: str) -> str:
    """A valid, lowercase module name for the adapter (no leading digit, alnum + underscore)."""
    name = re.sub(r"[^a-z0-9_]", "", (raw or "").lower().replace("-", "_").replace(" ", "_"))
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or name[0].isdigit():
        name = f"src_{name}" if name else "drafted"
    return name


def _class_name(code: str) -> str | None:
    """Name of the SourceAdapter class in the code (has `source` + `list_postings`)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        has_src = any(
            (isinstance(b, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "source"
                                                for t in b.targets))
            or (isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name)
                and b.target.id == "source")
            for b in node.body)
        has_list = any(isinstance(b, ast.FunctionDef) and b.name == "list_postings"
                       for b in node.body)
        if has_src and has_list:
            return node.name
    return None


def _register(root: Path, name: str, cls: str) -> None:
    """Add the adapter's import + registry entry to providers/sources/__init__.py, so a merged PR
    makes it usable. Import goes in alphabetically; the entry goes at the end of `_SOURCES`."""
    init = root / "src" / "resumaker" / "providers" / "sources" / "__init__.py"
    lines = init.read_text().splitlines()
    imp = f"from resumaker.providers.sources.{name} import {cls}"

    if imp not in lines:
        src_imports = [i for i, ln in enumerate(lines)
                       if ln.startswith("from resumaker.providers.sources.") and " import " in ln]
        insert_at = (src_imports[-1] + 1) if src_imports else 0
        for i in src_imports:
            mod = lines[i].split("from resumaker.providers.sources.")[1].split(" import")[0]
            if mod > name:
                insert_at = i
                break
        lines.insert(insert_at, imp)

    entry = f"    {cls}.source: {cls}(),"
    if entry.strip() not in {ln.strip() for ln in lines}:
        start = next(i for i, ln in enumerate(lines)
                     if ln.startswith("_SOURCES") and ln.rstrip().endswith("{"))
        close = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "}")
        lines.insert(close, entry)

    init.write_text("\n".join(lines) + "\n")


def process_draft(contract: dict, *, allow_hosts: list[str] | None = None,
                  repo_root: str | Path | None = None) -> dict:
    """If `contract` drafted an adapter, gate it and (on pass) write + register it for the PR.
    Returns an updated contract: `drafted` on success, `unresolved` if the gate rejects it.
    Non-draft contracts pass through unchanged."""
    code = contract.get("adapter_code")
    if not code:
        return contract

    root = Path(repo_root) if repo_root else _repo_root()
    board = dict(contract.get("board") or {})
    cls = _class_name(code)
    if not cls:
        return {"status": "unresolved", "note": "drafted adapter has no SourceAdapter class"}

    name = _safe_name(contract.get("adapter_name") or board.get("source") or "drafted")
    board.setdefault("source", name)

    # Don't let the agent shadow a source that already exists — it should have mapped to it.
    from resumaker.providers.sources import available_sources  # noqa: PLC0415
    if name in set(available_sources()):
        return {"status": "unresolved",
                "note": f"drafted adapter '{name}' clashes with an existing source; "
                        "the agent should have mapped to it"}

    v = gate.validate_adapter(code, board, allow_hosts=allow_hosts)
    if not v.get("ok"):
        detail = v.get("error") or v.get("errors")
        return {"status": "unresolved",
                "note": f"drafted adapter failed the gate ({v.get('stage')}): {detail}",
                "adapter_name": name}

    path = root / "src" / "resumaker" / "providers" / "sources" / f"{name}.py"
    path.write_text(code if code.endswith("\n") else code + "\n")
    _register(root, name, cls)
    _log.info("drafted adapter written + registered",
              extra={"name": name, "class": cls, "count": v.get("count")})
    return {
        "status": "drafted",
        "board": board,
        "evidence": {"count": v.get("count"), "well_formed": v.get("well_formed"),
                     "sample": v.get("sample")},
        "adapter_name": name,
        "note": (f"adapter '{name}' drafted + validated ({v.get('count')} live postings) and "
                 "written to providers/sources/; the onboarding workflow opens a review PR from it "
                 "(cloud path only). Merge + redeploy to enable this company."),
    }
