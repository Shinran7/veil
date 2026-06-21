"""Procedural SFX and MP3 background music via pygame.mixer."""

from __future__ import annotations

import array
import math
from pathlib import Path
from typing import TYPE_CHECKING

import config

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
        self.sfx_volume = config.DEFAULT_SFX_VOLUME
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
        if self.sfx_volume <= 0.0:
            return False
        interval = self._MIN_INTERVAL.get(name, 0.08)
        if self._cooldowns.get(name, 0.0) > 0.0:
            return False
        sound = self._sounds.get(name)
        if sound is None:
            return False
        sound.set_volume(self.sfx_volume)  # type: ignore[union-attr]
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


def _next_track_index(current: int, track_count: int) -> int:
    if track_count <= 0:
        return 0
    return (current + 1) % track_count


def _fade_should_start(elapsed: float, duration: float, fade_seconds: float) -> bool:
    if duration <= fade_seconds:
        return elapsed > 0.0
    return elapsed >= duration - fade_seconds


class MusicManager:
    """Round-robin MP3 playlist with end-of-track fade and a short gap."""

    def __init__(self) -> None:
        self.music_volume = config.DEFAULT_MUSIC_VOLUME
        self._tracks: list[Path] = []
        self._sounds: dict[Path, object] = {}
        self._durations: dict[Path, float] = {}
        self._track_index = 0
        self._channel: object | None = None
        self._active = False
        self._paused = False
        self._phase = "idle"
        self._elapsed = 0.0
        self._gap_remaining = 0.0
        self._fade_triggered = False

    def init(self) -> None:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=12, buffer=512)
        self._channel = pygame.mixer.Channel(config.MUSIC_CHANNEL)
        music_dir = Path(config.MUSIC_DIR)
        self._tracks = []
        self._sounds = {}
        self._durations = {}
        if not music_dir.is_dir():
            return
        for path in sorted(music_dir.glob("*.mp3")):
            try:
                sound = pygame.mixer.Sound(str(path))
            except pygame.error:
                continue
            self._tracks.append(path)
            self._sounds[path] = sound
            self._durations[path] = sound.get_length()

    def set_volume(self, volume: float) -> None:
        self.music_volume = max(0.0, min(1.0, volume))
        if self._channel and self._phase == "playing" and not self._fade_triggered:
            self._channel.set_volume(self.music_volume)  # type: ignore[union-attr]

    def tick(self, dt: float) -> None:
        if self._paused or not self._active or not self._tracks or self.music_volume <= 0.0:
            return
        if self._phase == "gap":
            self._gap_remaining -= dt
            if self._gap_remaining <= 0.0:
                self._track_index = _next_track_index(self._track_index, len(self._tracks))
                self._begin_track()
            return
        if self._phase != "playing":
            return
        self._elapsed += dt
        track = self._tracks[self._track_index]
        duration = self._durations[track]
        if not self._fade_triggered and _fade_should_start(
            self._elapsed, duration, config.MUSIC_FADE_OUT_SECONDS
        ):
            self._fade_triggered = True
            fade_ms = int(config.MUSIC_FADE_OUT_SECONDS * 1000)
            if self._channel:
                self._channel.fadeout(fade_ms)  # type: ignore[union-attr]
        if self._channel and not self._channel.get_busy():  # type: ignore[union-attr]
            self._begin_gap()

    def start(self) -> None:
        if self.music_volume <= 0.0 or not self._tracks:
            self.stop()
            return
        self._active = True
        self._paused = False
        if self._phase == "idle":
            self._begin_track()

    def stop(self) -> None:
        if self._channel:
            self._channel.stop()  # type: ignore[union-attr]
        self._active = False
        self._paused = False
        self._phase = "idle"
        self._elapsed = 0.0
        self._gap_remaining = 0.0
        self._fade_triggered = False
        self._track_index = 0

    def pause(self) -> None:
        self._paused = True
        if self._channel:
            self._channel.pause()  # type: ignore[union-attr]

    def unpause(self) -> None:
        if self.music_volume <= 0.0:
            self.stop()
            return
        if not self._tracks:
            return
        self._active = True
        self._paused = False
        if self._phase == "idle":
            self._begin_track()
            return
        if self._channel:
            self._channel.set_volume(self.music_volume)  # type: ignore[union-attr]
            if self._channel.get_busy():  # type: ignore[union-attr]
                self._channel.unpause()  # type: ignore[union-attr]
            elif self._phase == "playing":
                self._begin_track()

    def has_tracks(self) -> bool:
        return bool(self._tracks)

    def _begin_track(self) -> None:
        if not self._tracks or self._channel is None:
            self._phase = "idle"
            return
        track = self._tracks[self._track_index]
        sound = self._sounds[track]
        self._channel.set_volume(self.music_volume)  # type: ignore[union-attr]
        self._channel.play(sound, loops=0)  # type: ignore[union-attr]
        self._elapsed = 0.0
        self._fade_triggered = False
        self._phase = "playing"

    def _begin_gap(self) -> None:
        self._phase = "gap"
        self._gap_remaining = config.MUSIC_GAP_SECONDS
        self._elapsed = 0.0
        self._fade_triggered = False