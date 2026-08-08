"""CLI: `uv run python -m pocs.sponsorship "Google"` -> SponsorSignal JSON."""
from __future__ import annotations

import sys

from .scorer import sponsor_signal


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('usage: python -m pocs.sponsorship "Company Name"', file=sys.stderr)
        return 2
    company = " ".join(argv[1:])
    signal = sponsor_signal(company)
    print(signal.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
