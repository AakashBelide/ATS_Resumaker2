"""In-sandbox gate harness — runs the DRAFT adapter (untrusted) inside the locked box only.
  offline: import the draft's test, parse the captured fixture (no network).
  live:    instantiate the adapter and call list_postings against the live platform (egress
           allow-listed), print the count.
Mounts (read-only): /shim (faithful resumaker shim) + /draft (the generated files) on PYTHONPATH.
"""
from __future__ import annotations

import importlib
import json
import sys

sys.path.insert(0, "/shim")
sys.path.insert(0, "/draft")


def main() -> int:
    source, mode = sys.argv[1], sys.argv[2]
    if mode == "offline":
        t = importlib.import_module(f"test_{source}")
        t.test_parse()
        print("FIXTURE_TEST_PASS")
        return 0
    if mode == "live":
        board = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {"token": "", "extra": {}}
        m = importlib.import_module(source)
        cls = next(c for c in vars(m).values()
                   if isinstance(c, type) and getattr(c, "source", None) == source)
        posts = cls().list_postings(board.get("token", ""), **(board.get("extra") or {}))
        print(f"LIVE_COUNT {len(posts)}")
        for p in posts[:3]:
            print(f"  - {p.title} | {p.location}")
        return 0
    print(f"unknown mode {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
