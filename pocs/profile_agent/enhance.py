"""Flow 2 - profile enhancement chat.

The user provides extra info (free text, a big JSON/text dump, or answers to probes); the agent
proposes profile writes, each grounded in a verbatim user quote, and applies them on confirmation.
Thin orchestration around `agent.run_turn` - the runtime owns slash commands, caps, and the
anti-fabrication apply path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from resumaker.persistence import profile as profile_store
from resumaker.providers.llm import get_provider

from . import agent, store
from .prompts import ENHANCE_ANALYZE, GUARDRAIL

_SYSTEM = ("You are a careful career profile-enrichment assistant. You turn what the user tells you "
           "into structured profile updates. You never invent facts; you only record what they state.")


def start() -> store.RunState:
    return store.new_run("enhance")


def _recent_turns(st: store.RunState, k: int = 6) -> str:
    """The last k exchanges (excluding the current user message, which run_turn already appended) so
    the model can resolve 'it'/'that project' to what was just discussed."""
    prior = [t for t in st.history[:-1] if t.get("text")][-k:]
    if not prior:
        return "(start of conversation)"
    return "\n".join(f"{t['role']}: {t['text']}" for t in prior)


def _build_prompt(st: store.RunState, user_text: str) -> tuple[str, str]:
    prompt = ENHANCE_ANALYZE.format(guardrail=GUARDRAIL,
                                    profile_text=profile_store.profile_text()[:12000],
                                    recent_turns=_recent_turns(st)[:4000],
                                    user_message=user_text)
    return _SYSTEM, prompt


def say(st: store.RunState, message: str, *, llm: Any = None, profile_path: Path | None = None) -> str:
    llm = llm or get_provider(model="sonnet")   # configured default (Claude CLI local, API in cloud)
    return agent.run_turn(st, message, build_prompt=_build_prompt, llm=llm, profile_path=profile_path)
