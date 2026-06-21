"""Tests for scores module."""

from pathlib import Path

from scores import HighScoreTable


def test_high_score_table(tmp_path: Path) -> None:
    path = tmp_path / "scores.json"
    table = HighScoreTable(path=path)
    table.add(1000, 5, "balanced")
    table.add(500, 3, "light")
    table.load()
    assert len(table.entries) == 2
    assert table.entries[0].score == 1000