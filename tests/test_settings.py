"""Tests for persisted settings."""

from pathlib import Path

import config
from settings import GameSettings


def test_volume_persists(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    gs = GameSettings(sfx_volume=0.75, music_volume=0.5, path=path)
    gs.save()
    gs2 = GameSettings(path=path)
    gs2.load()
    assert gs2.sfx_volume == 0.75
    assert gs2.music_volume == 0.5


def test_adjust_volume_clamps_and_saves(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    gs = GameSettings(sfx_volume=0.1, music_volume=0.9, path=path)
    gs.save()
    assert gs.adjust_sfx_volume(-0.5) == 0.0
    assert gs.adjust_music_volume(0.2) == 1.0
    gs3 = GameSettings(path=path)
    gs3.load()
    assert gs3.sfx_volume == 0.0
    assert gs3.music_volume == 1.0


def test_migrates_sounds_disabled_to_zero_volumes(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"sounds_enabled": false}', encoding="utf-8")
    gs = GameSettings(path=path)
    gs.load()
    assert gs.sfx_volume == 0.0
    assert gs.music_volume == 0.0


def test_migrates_sounds_enabled_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"sounds_enabled": true}', encoding="utf-8")
    gs = GameSettings(path=path)
    gs.load()
    assert gs.sfx_volume == config.DEFAULT_SFX_VOLUME
    assert gs.music_volume == config.DEFAULT_MUSIC_VOLUME