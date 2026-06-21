"""Tests for persisted settings."""

from pathlib import Path

from settings import GameSettings


def test_toggle_sounds_persists(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    gs = GameSettings(sounds_enabled=True, path=path)
    gs.save()
    gs2 = GameSettings(path=path)
    gs2.load()
    assert gs2.sounds_enabled is True
    gs2.toggle_sounds()
    gs3 = GameSettings(path=path)
    gs3.load()
    assert gs3.sounds_enabled is False