"""Record headless AI arena bouts for behavior analysis.

Usage:
    python record_bouts.py
    python record_bouts.py --bouts 50 --seed 42
"""

from __future__ import annotations

import argparse
from pathlib import Path

from telemetry import format_report, simulate_ai_bouts, analyze_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Record Veil AI arena telemetry")
    parser.add_argument(
        "--bouts", type=int, default=20, help="Number of completed bouts to record"
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("telemetry") / "runs",
        help="Parent directory for session folders",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Print a quick summary when recording finishes",
    )
    args = parser.parse_args()

    run_dir = simulate_ai_bouts(
        bout_count=args.bouts,
        seed=args.seed,
        output_dir=args.output,
        width=args.width,
        height=args.height,
    )
    print(f"Recorded to {run_dir}")
    print("Note: same seed only replays identically on the same ai_revision (see session.json).")
    session_path = run_dir / "session.json"
    if session_path.exists():
        import json

        meta = json.loads(session_path.read_text(encoding="utf-8"))
        done = meta.get("bouts_completed", 0)
        target = meta.get("bout_target", done)
        if not meta.get("completed_fully", done >= target):
            print(
                f"Warning: run stopped early ({done}/{target} bouts, reason: {meta.get('stop_reason', 'unknown')})."
            )
    if args.analyze:
        report = analyze_run(run_dir)
        print()
        print(format_report(report, str(run_dir)))


if __name__ == "__main__":
    main()