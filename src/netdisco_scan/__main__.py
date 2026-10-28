"""Allow ``python -m netdisco_scan`` to run the scanner CLI."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
