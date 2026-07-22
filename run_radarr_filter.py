#!/usr/bin/env python3
"""Backward-compatible entry point.

The tool now lives in the ``radarr_janitor`` package with ``report``/``apply``
subcommands. Your old invocation still works and is mapped to a safe ``report``
(deletion now requires an explicit ``apply`` step):

    python3 run_radarr_filter.py --filter Horror --deletefile --addexclusion --minscore 85
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radarr_janitor.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
