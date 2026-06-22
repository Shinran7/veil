"""Audio rate limiting and volume tests."""

from pathlib import Path

import config
from audio import MusicManager, SoundManager, _fade_should_start, _next_track_index


def test_play_batch_caps_fire() -> None:
    sm = SoundManager()
    sm.init()
    sm.play_batch(["fire"] * 10)
    # Cooldown prevents machine-gun replay even within one batch
    assert not sm.play("fire")


def test_play_once_not_loop() -> None:
    sm = SoundManager()
    sm.init()
    assert sm.play("ui") is True
    assert sm.play("ui") is False


def test_fire_enemy_sound_exists() -> None:
    sm = SoundManager()
    sm.init()
    assert sm.play("fire_enemy") is True


def test_powerup_sounds_are_distinct() -> None:
    sm = SoundManager()
    sm.init()
    assert sm.play("powerup_shield") is True
    assert sm.play("powerup_fire_rate") is True
    assert sm.play("powerup_spread") is True


def test_zero_sfx_volume_mutes() -> None:
    sm = SoundManager()
    sm.init()
    sm.sfx_volume = 0.0
    assert sm.play("ui") is False


def test_music_manager_no_tracks_is_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "MUSIC_DIR", str(tmp_path / "music"))
    mm = MusicManager()
    mm.init()
    assert mm.has_tracks() is False
    mm.start()
    mm.stop()
    mm.set_volume(0.5)


def test_next_track_index_round_robins() -> None:
    assert _next_track_index(0, 4) == 1
    assert _next_track_index(3, 4) == 0
    assert _next_track_index(2, 0) == 0


def test_music_picks_random_start_index(monkeypatch) -> None:
    mm = MusicManager()
    mm._tracks = [Path("a.mp3"), Path("b.mp3"), Path("c.mp3")]
    mm._track_index = 0
    monkeypatch.setattr("audio.random.randrange", lambda n: 2)
    mm._pick_random_start_index()
    assert mm._track_index == 2


def test_fade_starts_before_track_end() -> None:
    assert _fade_should_start(177.0, 180.0, 3.0) is True
    assert _fade_should_start(176.0, 180.0, 3.0) is False
    assert _fade_should_start(0.5, 2.0, 3.0) is True