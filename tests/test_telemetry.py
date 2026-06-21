"""Telemetry recording and analysis tests."""

import json
from pathlib import Path

from telemetry import (
    TelemetryRecorder,
    analyze_run,
    simulate_ai_bouts,
)


def test_simulate_writes_frames_and_events(tmp_path: Path) -> None:
    run_dir = simulate_ai_bouts(
        bout_count=2, seed=7, output_dir=tmp_path, width=800, height=600
    )
    assert (run_dir / "frames.jsonl").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "session.json").exists()
    frames = (run_dir / "frames.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(frames) > 50
    session = json.loads((run_dir / "session.json").read_text(encoding="utf-8"))
    assert session["bouts_completed"] == 2


def test_analyze_detects_patterns(tmp_path: Path) -> None:
    run_dir = tmp_path / "mini"
    run_dir.mkdir()
    frames = run_dir / "frames.jsonl"
    events = run_dir / "events.jsonl"
    frames.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "t": 1,
                        "b": 1,
                        "id": 1,
                        "alive": True,
                        "m": "kite",
                        "bh": 1,
                        "h": 0.3,
                        "f": 0,
                        "td": 200,
                    }
                ),
                json.dumps(
                    {
                        "t": 2,
                        "b": 1,
                        "id": 1,
                        "alive": True,
                        "m": "panic",
                        "bh": 1,
                        "h": 0.2,
                        "f": 0,
                        "td": 150,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "t": 3,
                        "b": 1,
                        "type": "death",
                        "id": 1,
                        "v": "light",
                        "m": "panic",
                    }
                ),
                json.dumps(
                    {
                        "t": 4,
                        "b": 1,
                        "type": "bout_end",
                        "winner_v": "heavy",
                        "winner_wins": 3,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    report = analyze_run(run_dir)
    assert report.missed_tail_shots == 2
    assert report.flee_while_behind == 2
    assert report.deaths == 1
    assert report.deaths_by_mode["panic"] == 1
    assert report.variant_deaths["light"] == 1
    assert report.variant_bout_wins["heavy"] == 1
    assert report.variant_max_streak["heavy"] == 3
    text = __import__("telemetry").format_report(report)
    assert "Ship variant balance" in text
    assert "Heavy" in text


def test_recorder_bout_end_event(tmp_path: Path) -> None:
    from arena import Arena
    from game import GameState, Phase
    from ship import Ship, ShipVariant

    recorder = TelemetryRecorder(tmp_path / "rec")
    recorder.begin(1, 1, (800, 600))
    state = GameState()
    state.arena = Arena.from_window(800, 600)
    state.phase = Phase.PLAYING
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 100.0), ship_id=1)
    ship.champion_wins = 2
    state.all_ships = [ship]
    recorder.record_bout_end(state, ship)
    recorder.close()
    events = (tmp_path / "rec" / "events.jsonl").read_text(encoding="utf-8")
    assert "bout_end" in events
    assert "winner_wins" in events