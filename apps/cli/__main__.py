"""Enable `python -m apps.cli ...`."""
import sys

from apps.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
