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
# kinds whose write targets the `projects` LIST (addressed by title, not a dict key). These need
# name->index resolution before they can be written; the plain append path can't index a list by str.
PROJECT_BULLET_KINDS = {"add_bullet", "add_metric"}


# -- message classification --------------------------------------------------
def parse_slash(msg: str) -> tuple[str | None, str]:
    """Return (command, argument) if msg is a slash command, else (None, "")."""
    m = msg.strip()
    if not m.startswith("/"):
        return None, ""
    head, _, rest = m.partition(" ")
    head = head.lower()
    return (head, rest.strip()) if head in SLASH else ("__unknown__", m)


_AFFIRM_LEAD = ("sounds good", "go ahead", "do it", "yeah", "yep", "yup", "sure", "okay",
                "apply", "confirm", "approve", "approved", "yes", "ok", "y")
# a redirect/negation right after the "yes" means the user is correcting, NOT confirming
_CONTRA_LEAD = ("but", "actually", "no ", "not ", "except", "however", "instead", "wait",
                "change", "rather", "hold on", "don't", "dont", "under ", "make it")


def split_affirmative(msg: str) -> tuple[bool, str]:
    """Detect a message that STARTS with a clean confirmation, optionally carrying new info after it
    ("yes, I built it in 2026"). Returns (True, remainder) - remainder is '' for a bare "yes". Returns
    (False, '') when it isn't a leading confirmation, or when a contrast word right after it
    ("yes but...", "yes, actually...") signals a redirect rather than a confirmation."""
    m = msg.strip()
    low = m.lower()
    for tok in _AFFIRM_LEAD:                      # ordered longest-ish first so "yeah" beats "y"
        if low == tok:
            return True, ""
        if not low.startswith(tok) or low[len(tok):len(tok) + 1].isalnum():
            continue                              # must end on a word boundary, not "yesterday"
        rest = m[len(tok):].lstrip(" ,.!;:-").strip()
        rl = rest.lower()
        if rl.startswith("and "):
            rest, rl = rest[4:].strip(), rl[4:]
        if not rest:
            return True, ""
        if any(rl == c.strip() or rl.startswith(c) for c in _CONTRA_LEAD):
            return False, ""                      # "yes but ..." -> let the model handle the redirect
        return True, rest
    return False, ""


def is_affirmative(msg: str) -> bool:
    ok, rest = split_affirmative(msg)
    return ok and not rest


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


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:48] or "project"


def _coerce_project(value: Any) -> dict:
    """Normalize a proposed project into the profile.json project shape (id/title/organization/
    date/url/bullets[{text}]). Accepts a bare title string or a partial dict."""
    proj = dict(value) if isinstance(value, dict) else {"title": str(value)}
    for k in ("title", "organization", "date", "url"):
        proj.setdefault(k, "")
    proj["bullets"] = [b if isinstance(b, dict) else {"text": str(b)}
                       for b in (proj.get("bullets") or [])]
    proj.setdefault("id", _slug(proj["title"]))
    return proj


def _resolve_project_index(projects: list, ref: Any) -> int | None:
    """Map a project reference (int index, int-like string, or a partial/whole title) to an index in
    the projects list. Title match is whitespace/case-insensitive and tolerates the '2.0'-style
    suffix the model sometimes drops."""
    if isinstance(ref, bool):
        return None
    if isinstance(ref, int):
        return ref if -len(projects) <= ref < len(projects) else None
    s = str(ref).strip()
    if s.lstrip("-").isdigit():
        i = int(s)
        return i if -len(projects) <= i < len(projects) else None
    want = _norm(s)
    titles = [_norm(p.get("title", "")) for p in projects]
    for i, t in enumerate(titles):          # exact first
        if t == want:
            return i
    for i, t in enumerate(titles):          # then containment either way
        if want and (want in t or t in want):
            return i
    return None


def apply_proposal(p: Proposal, *, profile_path: Path | None = None) -> Applied | None:
    """Route a confirmed proposal to the right audited writer. Append-kinds extend a list; scalar
    kinds replace. Preferences and house rules go to their own docs. Returns None when the proposal
    is a no-op (e.g. re-adding a project that already exists with no new bullets)."""
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

    # profile.json writes (append or replace) -> update_profile_fact (audited). Read the profile
    # FRESH from the same file update_profile_fact writes to (never the lru-cached load_profile),
    # so chained writes in one confirmation batch see each other - otherwise a stale snapshot makes
    # a whole-list overwrite drop the previous write and project lookups miss just-added projects.
    import json as _json
    from pathlib import Path as _Path

    from resumaker.config import get_settings as _get_settings
    _pf = profile_path or _get_settings().profile_path
    prof = _json.loads(_Path(_pf).read_text())
    kw = {"profile_path": profile_path} if profile_path else {}

    # `projects` is a LIST addressed by title. A new project is appended - but the model tends to
    # re-propose the SAME project every turn, so make it idempotent: if the title already exists,
    # fold any proposed bullets into that project instead of creating a duplicate.
    if p.kind == "add_project":
        proj = _coerce_project(p.value)
        projects = list(prof.get("projects") or [])
        existing = _resolve_project_index(projects, proj["title"]) if proj["title"] else None
        if existing is not None:
            add_bullets = proj.get("bullets") or []
            if not add_bullets:
                return None            # already present, nothing new to write -> skipped, not an error
            old = list(projects[existing].get("bullets") or [])
            new_value = old + add_bullets
            write_path = ["projects", existing, "bullets"]
            manager.update_profile_fact(write_path, new_value,
                                        reason=f"profile-agent: bullets for {proj['title']!r}",
                                        source="profile-agent", **kw)
            return Applied("add_bullet", write_path, old, new_value,
                           f"{len(add_bullets)} bullet(s) -> {proj['title']}")
        new_value = projects + [proj]
        manager.update_profile_fact(["projects"], new_value,
                                    reason=f"profile-agent: add project {proj['title']!r}",
                                    source="profile-agent", **kw)
        return Applied("add_project", ["projects"], projects, new_value, p.preview or proj["title"])

    if p.kind in PROJECT_BULLET_KINDS and p.path and p.path[0] == "projects":
        projects = prof.get("projects") or []
        ref = p.path[1] if len(p.path) > 1 else (p.preview or "")
        idx = _resolve_project_index(projects, ref)
        if idx is None:
            raise ValueError(f"no project matching {ref!r} to add this to - add the project first")
        bullet = p.value if isinstance(p.value, dict) else {"text": str(p.value)}
        write_path = ["projects", idx, "bullets"]
        old = list(projects[idx].get("bullets") or [])
        new_value = old + [bullet]
        manager.update_profile_fact(write_path, new_value,
                                    reason=f"profile-agent: {p.preview or p.kind}",
                                    source="profile-agent", **kw)
        return Applied(p.kind, write_path, old, new_value,
                       p.preview or bullet.get("text", p.kind)[:60])

    old = _get_by_path(prof, p.path)
    # append-kinds extend a list; scalar kinds (edit_summary, add_equivalence, ...) replace at path
    new_value = list(old or []) + [p.value] if p.kind in APPEND_KINDS else p.value
    manager.update_profile_fact(p.path, new_value, reason=f"profile-agent: {p.preview or p.kind}",
                                source="profile-agent", **kw)
    return Applied(p.kind, p.path, old, new_value, p.preview or p.kind)


def apply_pending(st: RunState, *, profile_path: Path | None = None) -> int:
    """Apply every pending proposal, record each for /undo, clear the queue. Returns the count that
    succeeded. A proposal that fails to write is skipped (never 500s the turn); its label is recorded
    in `st.meta['apply_errors']` so the caller can tell the user which ones didn't land."""
    n = 0
    errors: list[str] = []
    for pd in list(st.pending):
        try:
            applied = apply_proposal(Proposal(**pd), profile_path=profile_path)
        except Exception as e:  # noqa: BLE001 - one bad proposal must not lose the rest of the batch
            label = pd.get("preview") or pd.get("kind", "change")
            errors.append(label)
            st.add_event("apply", "error", f"{label}: {e}")
            continue
        if applied is None:                     # no-op (e.g. project already present) - not counted
            st.add_event("apply", "skip", pd.get("preview") or pd.get("kind", "change"))
            continue
        st.applied.append(asdict(applied))
        st.add_event("apply", "ok", applied.detail)
        n += 1
    st.pending = []
    st.meta["apply_errors"] = errors
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
def _analyze_turn(st: RunState, message: str, *,
                  build_prompt: Callable[[RunState, str], tuple[str, str]], llm: Any) -> str:
    """One LLM analysis turn: build the prompt, call the model, validate proposals against the
    anti-fabrication gate, set pending, and craft the reply. The caller has already counted the turn
    and checked caps."""
    system, prompt = build_prompt(st, message)
    data = llm.complete_json(prompt, system=system, task="profile-agent")
    raw = data.get("proposals", []) if isinstance(data, dict) else []
    accepted, rejected = to_proposals(raw, message)
    st.pending = [asdict(p) for p in accepted]
    if rejected:
        st.add_event("filter", "ok", f"dropped {len(rejected)} ungrounded proposal(s)")
    reply = (data.get("reply") or data.get("question") or "").strip() if isinstance(data, dict) else ""
    if not accepted and not (isinstance(data, dict) and data.get("question")):
        st.meta["no_progress"] = st.meta.get("no_progress", 0) + 1
        if st.meta["no_progress"] >= NO_PROGRESS_LIMIT:
            reply += "\n(We don't seem to be adding anything new - say /done to finish.)"
    else:
        st.meta["no_progress"] = 0
    if accepted and "approve" not in reply.lower() and "apply" not in reply.lower():
        reply += "  Reply 'yes' to apply, or /skip."
    return reply


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
    # a confirmation (possibly with new info tacked on) only counts when something is pending
    aff_ok, aff_rest = split_affirmative(message) if (cmd is None and st.pending) else (False, "")

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
            errs = st.meta.get("apply_errors") or []
            tail = f" Couldn't apply {len(errs)}: {'; '.join(errs)}." if errs else ""
            reply = f"Applied {applied} change(s).{tail} (/generate is only available in a match/gap chat.)"
        else:
            reply = on_generate(st)
            st.state = "done"
    elif cmd == "__unknown__":
        reply = "Unknown command. Try /help."
    # 2) confirmation -> apply pending. If the user tacked new info onto the "yes" ("yes, I built it
    #    in 2026"), don't lose it: analyze the remainder in the SAME turn so it lands, with the
    #    conversation context the prompt now carries so "it" binds to the right project.
    elif aff_ok:
        n = apply_pending(st, profile_path=profile_path)
        errs = st.meta.get("apply_errors") or []
        st.meta["no_progress"] = 0
        reply = f"Applied {n} change(s)."
        if errs:
            reply += f" Couldn't apply {len(errs)}: {'; '.join(errs)}."
        if aff_rest and cap_status(st)[0]:
            st.meta["turns_used"] = st.meta.get("turns_used", 0) + 1
            reply = (reply + " " + _analyze_turn(st, aff_rest, build_prompt=build_prompt, llm=llm)).strip()
        elif n:
            reply += " Anything else, or /done?"
    # 3) otherwise: a real message -> one LLM analysis turn
    else:
        ok, reason = cap_status(st)
        if not ok:
            st.state = "done"
            reply = f"Wrapping up - {reason}. Applied {len(st.applied)} change(s)."
        else:
            st.meta["turns_used"] = st.meta.get("turns_used", 0) + 1
            reply = _analyze_turn(st, message, build_prompt=build_prompt, llm=llm)

    st.add_turn("agent", reply)
    store.save(st)
    return reply

