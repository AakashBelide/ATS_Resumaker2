"""Back-compat entry point. The real logic lives in orchestrator.py + cli.py.
Usage: uv run python run_pipeline.py <jd_url>   (equivalent to `python -m cli run <url>`)
"""
import sys

from cli import main

if __name__ == "__main__":
    sys.exit(main(["run", *sys.argv[1:]]))
