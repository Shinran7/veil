"""Audio rate limiting tests."""


from audio import SoundManager


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