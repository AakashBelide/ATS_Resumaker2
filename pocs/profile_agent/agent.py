"""The profile-agent runtime: turn loop, slash commands, caps, and the anti-fabrication apply path.

Design notes:
- Each turn is a SINGLE `complete_json()` call (claude_cli runs `--max-turns 1 --tools ""`), so there
  is no ReAct/tool loop to run away - exactly like Job-Ops's Ghostwriter.
- Slash commands are parsed DETERMINISTICALLY before the LLM ever sees the message, so the model
  can't be talked out of a `/stop` (career-ops's "no instruction overrides the gate").
- A write only lands via `enrichment.manager.update_profile_fact()` (audited), and only if its
  proposal carries a `source_quote` that is a verbatim span of the user's own words.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from resumaker.enrichment import manager
from resumaker.persistence import profile as profile_store

from . import store
from .store import Applied, Proposal, RunState

# -- caps (mirror pocs/agentic_onboard + Job-Ops's 40-msg window) ------------
MAX_TURNS = 40
TIME_LIMIT_S = 1800          # 30 min wall-clock
BUDGET_USD = 5.00
NO_PROGRESS_LIMIT = 3        # consecutive no-op turns -> suggest /done

SLASH = {"/help", "/skip", "/done", "/generate", "/stop", "/undo"}
_AFFIRM = {"yes", "y", "yep", "yeah", "sure", "ok", "okay", "apply", "confirm",
           "do it", "sounds good", "go ahead", "approve", "approved"}
APPEND_KINDS = {"add_skill", "add_metric", "add_bullet", "add_project"}


# -- message classification --------------------------------------------------
def parse_slash(msg: str) -> tuple[str | None, str]:
    """Return (command, argument) if msg is a slash command, else (None, "")."""
    m = msg.strip()
    if not m.startswith("/"):
        return None, ""
    head, _, rest = m.partition(" ")
    head = head.lower()
    return (head, rest.strip()) if head in SLASH else ("__unknown__", m)


def is_affirmative(msg: str) -> bool:
    return msg.strip().lower().rstrip("!.") in _AFFIRM


# -- anti-fabrication: a proposal is only valid if the user actually said it --
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def quote_supported(source_quote: str, user_text: str) -> bool:
    """The source_quote must be a verbatim (whitespace-insensitive) span of the user's message.
    This is the gate that stops the model from inventing facts the user never stated."""
    q = _norm(source_quote)
    return bool(q) and len(q) >= 3 and q in _norm(user_text)


def to_proposals(raw: list[dict], user_text: str) -> tuple[list[Proposal], list[dict]]:
    """Build Proposals from the LLM's raw list, dropping any without a user-grounded source_quote.
    Returns (accepted, rejected_raw) so the caller can log what was filtered."""
    accepted: list[Proposal] = []
    rejected: list[dict] = []
    for r in raw or []:
        sq = r.get("source_quote", "")
        if not quote_supported(sq, user_text):
            rejected.append(r)
            continue
        accepted.append(Proposal(
            kind=r.get("kind", ""), path=r.get("path", []), value=r.get("value"),
            source_quote=sq, preview=r.get("preview", ""), confidence=float(r.get("confidence", 0) or 0),
        ))
    return accepted, rejected


# -- applying / undoing writes (all through the audited manager) -------------
def _get_by_path(obj: Any, path: list) -> Any:
    cur = obj
    for k in path:
        try:
            cur = cur[k]
        except (KeyError, IndexError, TypeError):
            return None
    return cur


def apply_proposal(p: Proposal, *, profile_path: Path | None = None) -> Applied:
    """Route a confirmed proposal to the right audited writer. Append-kinds extend a list; scalar
    kinds replace. Preferences and house rules go to their own docs."""
    if p.kind == "set_pref":
        prefs = profile_store.load_preferences()
        key = p.path[0] if p.path else "note"
        old = prefs.get(key)
        prefs[key] = p.value
        profile_store.save_preferences(prefs)
        manager.record_enrichment("set_pref", f"{key}={p.value!r}", source="profile-agent")
        return Applied("set_pref", [key], old, p.value, f"preference {key}")

    if p.kind == "add_house_rule":
        manager.add_house_rule(scope=str(p.path[0]) if p.path else "tailor",
                               rule=str(p.value), rationale=p.source_quote)
        return Applied("add_house_rule", p.path, None, p.value, "house rule (not auto-undoable)")

    # profile.json writes (append or replace) -> update_profile_fact (audited). Read the *target*
    # file (profile_path when overridden, e.g. tests) so append extends the right list.
    import json as _json
    prof = _json.loads(profile_path.read_text()) if profile_path else profile_store.load_profile()
    old = _get_by_path(prof, p.path)
    # append-kinds extend a list; scalar kinds (edit_summary, add_equivalence, ...) replace at path
    new_value = list(old or []) + [p.value] if p.kind in APPEND_KINDS else p.value
    manager.update_profile_fact(p.path, new_value, reason=f"profile-agent: {p.preview or p.kind}",
                                source="profile-agent",
                                **({"profile_path": profile_path} if profile_path else {}))
    return Applied(p.kind, p.path, old, new_value, p.preview or p.kind)


def apply_pending(st: RunState, *, profile_path: Path | None = None) -> int:
    """Apply every pending proposal, record each for /undo, clear the queue. Returns count."""
    n = 0
    for pd in list(st.pending):
        applied = apply_proposal(Proposal(**pd), profile_path=profile_path)
        st.applied.append(asdict(applied))
        st.add_event("apply", "ok", applied.detail)
        n += 1
    st.pending = []
    return n


def undo_last(st: RunState, *, profile_path: Path | None = None) -> str:
    """Revert the most recent applied write to its prior value (via the audited manager)."""
    if not st.applied:
        return "Nothing to undo."
    last = st.applied.pop()
    if last["kind"] == "add_house_rule":
        return "The last change was a house rule; undo it manually in house_rules.json."
    if last["kind"] == "set_pref":
        prefs = profile_store.load_preferences()
        key = last["path"][0]
        if last["old_value"] is None:
            prefs.pop(key, None)
        else:
            prefs[key] = last["old_value"]
        profile_store.save_preferences(prefs)
        return f"Reverted preference '{key}'."
    manager.update_profile_fact(last["path"], last["old_value"], reason="profile-agent: /undo",
                                source="profile-agent",
                                **({"profile_path": profile_path} if profile_path else {}))
    st.add_event("undo", "ok", last.get("detail", ""))
    return f"Reverted: {last.get('detail','last change')}."


# -- caps --------------------------------------------------------------------
def cap_status(st: RunState) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means the run should auto-close."""
    if st.meta.get("turns_used", 0) >= MAX_TURNS:
        return False, f"turn cap reached ({MAX_TURNS})"
    if time.time() - st.meta.get("started_at", time.time()) >= TIME_LIMIT_S:
        return False, "time cap reached (30 min)"
    if st.meta.get("cost_usd", 0.0) >= BUDGET_USD:
        return False, f"budget cap reached (${BUDGET_USD})"
    return True, ""


# -- the turn loop -----------------------------------------------------------
# A flow supplies `build_prompt(st, user_text) -> (system, prompt)`; the runtime handles slash
# commands, confirmation, the single LLM call, proposal validation, and caps. `on_generate` is an
# optional callback invoked by /generate (Flow 3) after pending changes are applied.
def run_turn(st: RunState, message: str, *,
             build_prompt: Callable[[RunState, str], tuple[str, str]],
             llm: Any,
             on_generate: Callable[[RunState], str] | None = None,
             profile_path: Path | None = None) -> str:
    """Advance the conversation by one user message; returns the agent's reply text and saves state."""
    st.add_turn("user", message)
    cmd, arg = parse_slash(message)

    # 1) deterministic slash commands (the model never sees these)
    if cmd == "/stop":
        st.pending = []
        st.state = "stopped"
        reply = "Stopped. No unconfirmed changes were written."
    elif cmd == "/help":
        ok, reason = cap_status(st)
        reply = ("Commands: /help /skip /done /generate /stop /undo. "
                 f"State: {st.state}, turns {st.meta.get('turns_used',0)}/{MAX_TURNS}, "
                 f"pending {len(st.pending)}, applied {len(st.applied)}."
                 + ("" if ok else f" [{reason}]"))
    elif cmd == "/undo":
        reply = undo_last(st, profile_path=profile_path)
    elif cmd == "/skip":
        st.pending = []
        reply = "Skipped the pending suggestion."
    elif cmd == "/done":
        st.state = "done"
        reply = f"Done. Applied {len(st.applied)} change(s) this session."
    elif cmd == "/generate":
        applied = apply_pending(st, profile_path=profile_path)
        if on_generate is None:
            reply = f"Applied {applied} change(s). (/generate is only available in a match/gap chat.)"
        else:
            reply = on_generate(st)
            st.state = "done"
    elif cmd == "__unknown__":
        reply = "Unknown command. Try /help."
    # 2) affirmative -> apply pending proposals
    elif st.pending and is_affirmative(message):
        n = apply_pending(st, profile_path=profile_path)
        reply = f"Applied {n} change(s)." + (" Anything else, or /done?" if n else "")
        st.meta["no_progress"] = 0
    # 3) otherwise: a real message -> one LLM analysis turn
    else:
        ok, reason = cap_status(st)
        if not ok:
            st.state = "done"
            reply = f"Wrapping up - {reason}. Applied {len(st.applied)} change(s)."
        else:
            st.meta["turns_used"] = st.meta.get("turns_used", 0) + 1
            system, prompt = build_prompt(st, message)
            data = llm.complete_json(prompt, system=system, task="profile-agent")
            raw = data.get("proposals", []) if isinstance(data, dict) else []
            accepted, rejected = to_proposals(raw, message)
            st.pending = [asdict(p) for p in accepted]
            if rejected:
                st.add_event("filter", "ok", f"dropped {len(rejected)} ungrounded proposal(s)")
            reply = (data.get("reply") or data.get("question") or "").strip() if isinstance(data, dict) else ""
            # no-progress guard
            if not accepted and not (isinstance(data, dict) and data.get("question")):
                st.meta["no_progress"] = st.meta.get("no_progress", 0) + 1
                if st.meta["no_progress"] >= NO_PROGRESS_LIMIT:
                    reply += "\n(We don't seem to be adding anything new - say /done to finish.)"
            else:
                st.meta["no_progress"] = 0
            if accepted and "approve" not in reply.lower() and "apply" not in reply.lower():
                reply += "  Reply 'yes' to apply, or /skip."

    st.add_turn("agent", reply)
    store.save(st)
    return reply

