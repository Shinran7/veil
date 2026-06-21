"""Analyze recorded Veil AI telemetry.

Usage:
    python analyze_bouts.py
    python analyze_bouts.py telemetry/runs/session-20260620-120000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from telemetry import analyze_directory, analyze_run, format_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Veil AI telemetry")
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("telemetry") / "runs",
        help="Session folder or parent directory of sessions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain summary",
    )
    args = parser.parse_args()

    if (args.path / "frames.jsonl").exists():
        report = analyze_run(args.path)
        label = str(args.path)
    else:
        report = analyze_directory(args.path)
        label = str(args.path)

    if args.json:
        from dataclasses import asdict

        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report, label))


if __name__ == "__main__":
    main()