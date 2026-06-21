"""Procedural sound effects via pygame.mixer."""

from __future__ import annotations

import array
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pygame


def _make_tone(
    frequency: float,
    duration: float = 0.08,
    volume: float = 0.25,
    sample_rate: int = 22050,
) -> "pygame.mixer.Sound":
    import pygame

    count = int(sample_rate * duration)
    buf = array.array("h", [0] * count)
    for i in range(count):
        t = i / sample_rate
        envelope = 1.0 - (i / count)
        sample = volume * 32767 * envelope * math.sin(2 * math.pi * frequency * t)
        buf[i] = int(sample)
    return pygame.mixer.Sound(buffer=buf)


def _make_dual_tone(
    frequency_a: float,
    frequency_b: float,
    duration: float = 0.1,
    volume: float = 0.14,
    sample_rate: int = 44100,
) -> "pygame.mixer.Sound":
    import pygame

    count = int(sample_rate * duration)
    buf = array.array("h", [0] * count)
    for i in range(count):
        t = i / sample_rate
        attack = min(1.0, i / max(1, int(sample_rate * 0.012)))
        release = 1.0 - (i / count)
        envelope = attack * release
        wave = (
            0.58 * math.sin(2 * math.pi * frequency_a * t)
            + 0.42 * math.sin(2 * math.pi * frequency_b * t)
        )
        sample = volume * 32767 * envelope * wave
        buf[i] = int(max(-32767, min(32767, int(sample))))
    return pygame.mixer.Sound(buffer=buf)


class SoundManager:
    """Rate-limited one-shot SFX — prevents machine-gun audio stacking."""

    _FRAME_LIMITS: dict[str, int] = {
        "fire": 2,
        "fire_enemy": 2,
        "hit": 2,
        "explosion": 2,
        "powerup_shield": 1,
        "powerup_fire_rate": 1,
        "powerup_spread": 1,
        "boss_pulse": 1,
        "ui": 2,
        "wave": 1,
    }

    _MIN_INTERVAL: dict[str, float] = {
        "fire": 0.07,
        "fire_enemy": 0.07,
        "hit": 0.09,
        "explosion": 0.12,
        "powerup_shield": 0.15,
        "powerup_fire_rate": 0.15,
        "powerup_spread": 0.15,
        "boss_pulse": 0.35,
        "ui": 0.05,
        "wave": 0.2,
    }

    def __init__(self) -> None:
        self.enabled = True
        self._sounds: dict[str, object] = {}
        self._cooldowns: dict[str, float] = {}

    def init(self) -> None:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=12, buffer=512)
        pickup_vol = 0.13
        self._sounds = {
            "fire": _make_tone(920, 0.07, 0.22, sample_rate=44100),
            "fire_enemy": _make_tone(720, 0.05, 0.04, sample_rate=44100),
            "hit": _make_tone(240, 0.05, 0.07, sample_rate=44100),
            "explosion": _make_tone(90, 0.22, 0.28, sample_rate=44100),
            "powerup_shield": _make_dual_tone(392, 523, 0.15, pickup_vol),
            "powerup_fire_rate": _make_dual_tone(740, 988, 0.07, pickup_vol * 0.92),
            "powerup_spread": _make_dual_tone(330, 660, 0.11, pickup_vol),
            "boss_pulse": _make_tone(140, 0.18, 0.2, sample_rate=44100),
            "ui": _make_tone(440, 0.05, 0.18, sample_rate=44100),
            "wave": _make_tone(330, 0.15, 0.22, sample_rate=44100),
        }

    def tick(self, dt: float) -> None:
        for name in list(self._cooldowns):
            self._cooldowns[name] = max(0.0, self._cooldowns[name] - dt)

    def play(self, name: str) -> bool:
        if not self.enabled:
            return False
        interval = self._MIN_INTERVAL.get(name, 0.08)
        if self._cooldowns.get(name, 0.0) > 0.0:
            return False
        sound = self._sounds.get(name)
        if sound is None:
            return False
        sound.play(0)  # type: ignore[union-attr]  # 0 = play once; -1 loops forever
        self._cooldowns[name] = interval
        return True

    def play_batch(self, names: list[str]) -> None:
        """Play a frame's sound queue with per-type caps."""
        played: dict[str, int] = {}
        for name in names:
            limit = self._FRAME_LIMITS.get(name, 1)
            if played.get(name, 0) >= limit:
                continue
            if self.play(name):
                played[name] = played.get(name, 0) + 1