"""POC CLI for the profile chat-agent. Run from the repo root so `resumaker` is importable:

  # Flow 1 - onboarding intake (parse a resume, optionally a LinkedIn PDF)
  uv run python -m pocs.profile_agent.cli intake Resources/Aakash_Belide_Resume.docx \
        --linkedin Resources/LinkedIn_Profile.pdf
  uv run python -m pocs.profile_agent.cli intake-apply <run_id>      # promote parsed -> profile.json

  # Flow 2 - enhancement chat
  uv run python -m pocs.profile_agent.cli enhance                    # prints a new run_id
  uv run python -m pocs.profile_agent.cli say <run_id> "At Granite I stood up Qdrant, cut latency 40%"
  uv run python -m pocs.profile_agent.cli say <run_id> "yes"         # confirm the proposal
  uv run python -m pocs.profile_agent.cli say <run_id> "/done"

  # Flow 3 - match-time gap clarification -> re-match -> generate
  uv run python -m pocs.profile_agent.cli gapchat <report_run_id>
  uv run python -m pocs.profile_agent.cli say <run_id> "Yes, I used Kafka at Bajaj for the fraud stream"
  uv run python -m pocs.profile_agent.cli say <run_id> "/generate"

  uv run python -m pocs.profile_agent.cli watch <run_id>
  uv run python -m pocs.profile_agent.cli stop <run_id>
"""
from __future__ import annotations

import argparse
import sys

from . import enhance, gapchat, intake, store


def _print_state(st: store.RunState) -> None:
    print(f"run_id = {st.run_id}   state = {st.state}   mode = {st.mode}")
    for e in st.events[-6:]:
        print(f"  [{e['status']:>10}] {e['stage']}: {e['detail']}")
    if st.meta.get("thin_spots"):
        print("\nThin spots to clarify:")
        for s in st.meta["thin_spots"]:
            print(f"  - {s}")
    if st.meta.get("preferences_to_ask"):
        print("\nPreference questions:")
        for q in st.meta["preferences_to_ask"]:
            print(f"  - {q}")
    if st.pending:
        print("\nPending (reply 'yes' to apply, '/skip' to drop):")
        for p in st.pending:
            print(f"  - {p.get('preview') or p.get('kind')}  (quote: \"{p.get('source_quote','')[:60]}\")")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="profile-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_in = sub.add_parser("intake", help="parse a resume (+optional LinkedIn PDF) into a profile")
    p_in.add_argument("resume")
    p_in.add_argument("--linkedin", default=None)

    sub.add_parser("intake-apply", help="promote a run's parsed profile to canonical profile.json").add_argument("run_id")
    sub.add_parser("enhance", help="start a profile-enhancement chat")
    p_gap = sub.add_parser("gapchat", help="start a gap-clarification chat for a completed match")
    p_gap.add_argument("report_run_id")

    p_say = sub.add_parser("say", help="send a message or slash command to a run")
    p_say.add_argument("run_id")
    p_say.add_argument("message")

    sub.add_parser("watch", help="print a run's state").add_argument("run_id")
    sub.add_parser("stop", help="stop a run").add_argument("run_id")

    args = ap.parse_args(argv)

    if args.cmd == "intake":
        st = intake.run_intake(args.resume, linkedin_path=args.linkedin)
        _print_state(st)
        print(f"\nNext: review, then `intake-apply {st.run_id}` to write profile.json, "
              f"or `say`/`enhance` to fill thin spots.")
        return 0
    if args.cmd == "intake-apply":
        intake.apply_parsed_to_profile(args.run_id)
        print("Promoted parsed profile to canonical profile.json.")
        return 0
    if args.cmd == "enhance":
        st = enhance.start()
        print(f"Started enhance run {st.run_id}. Now: `say {st.run_id} \"...\"`")
        return 0
    if args.cmd == "gapchat":
        st = gapchat.start(args.report_run_id)
        _print_state(st)
        print(f"\nStarted gap chat {st.run_id}. Talk through the gaps, then `say {st.run_id} /generate`.")
        return 0
    if args.cmd == "say":
        st = store.load(args.run_id)
        if st.state in ("stopped", "done", "error"):
            print(f"Run is {st.state}; start a new one.")
            return 1
        fn = {"enhance": enhance.say, "gapchat": gapchat.say}.get(st.mode)
        if fn is None:
            print(f"Mode {st.mode!r} is not conversational (use intake/intake-apply).")
            return 1
        reply = fn(st, args.message)
        print(f"agent> {reply}")
        _print_state(store.load(args.run_id))
        return 0
    if args.cmd == "watch":
        _print_state(store.load(args.run_id))
        return 0
    if args.cmd == "stop":
        st = store.load(args.run_id)
        st.state = "stopped"
        st.pending = []
        store.save(st)
        print("stopped")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
