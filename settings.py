"""Persisted game settings (volume, display, etc.)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, round(value, 2)))


@dataclass
class GameSettings:
    sfx_volume: float = config.DEFAULT_SFX_VOLUME
    music_volume: float = config.DEFAULT_MUSIC_VOLUME
    work_mode: bool = False
    borderless_window: bool = False
    window_width: int = config.DEFAULT_WIDTH
    window_height: int = config.DEFAULT_HEIGHT
    path: Path = field(default_factory=lambda: Path(config.SETTINGS_FILE))

    def to_json(self) -> dict[str, Any]:
        return {
            "sfx_volume": self.sfx_volume,
            "music_volume": self.music_volume,
            "work_mode": self.work_mode,
            "borderless_window": self.borderless_window,
            "window_width": self.window_width,
            "window_height": self.window_height,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any], path: Path | None = None) -> GameSettings:
        sfx, music = cls._parse_volumes(data)
        return cls(
            sfx_volume=sfx,
            music_volume=music,
            work_mode=bool(data.get("work_mode", False)),
            borderless_window=bool(data.get("borderless_window", False)),
            window_width=int(data.get("window_width", config.DEFAULT_WIDTH)),
            window_height=int(data.get("window_height", config.DEFAULT_HEIGHT)),
            path=path or Path(config.SETTINGS_FILE),
        )

    @staticmethod
    def _parse_volumes(data: dict[str, Any]) -> tuple[float, float]:
        if "sfx_volume" in data or "music_volume" in data:
            return (
                _clamp_volume(float(data.get("sfx_volume", config.DEFAULT_SFX_VOLUME))),
                _clamp_volume(float(data.get("music_volume", config.DEFAULT_MUSIC_VOLUME))),
            )
        if "sounds_enabled" in data and not bool(data["sounds_enabled"]):
            return 0.0, 0.0
        return config.DEFAULT_SFX_VOLUME, config.DEFAULT_MUSIC_VOLUME

    def save(self) -> None:
        self.path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            loaded = self.from_json(data, self.path)
            self.sfx_volume = loaded.sfx_volume
            self.music_volume = loaded.music_volume
            self.work_mode = loaded.work_mode
            self.borderless_window = loaded.borderless_window
            self.window_width = max(320, loaded.window_width)
            self.window_height = max(240, loaded.window_height)

    def adjust_sfx_volume(self, delta: float) -> float:
        self.sfx_volume = _clamp_volume(self.sfx_volume + delta)
        self.save()
        return self.sfx_volume

    def adjust_music_volume(self, delta: float) -> float:
        self.music_volume = _clamp_volume(self.music_volume + delta)
        self.save()
        return self.music_volume

    def toggle_work_mode(self) -> bool:
        self.work_mode = not self.work_mode
        self.save()
        return self.work_mode

    def toggle_borderless(self) -> bool:
        self.borderless_window = not self.borderless_window
        self.save()
        return self.borderless_window

    def remember_window_size(self, width: int, height: int) -> None:
        self.window_width = max(config.WINDOW_MIN_WIDTH, int(width))
        self.window_height = max(config.WINDOW_MIN_HEIGHT, int(height))
        self.window_width = min(config.WINDOW_MAX_WIDTH, self.window_width)
        self.window_height = min(config.WINDOW_MAX_HEIGHT, self.window_height)
        self.save()

    def adjust_window_size(self, delta_w: int, delta_h: int) -> tuple[int, int]:
        self.window_width = max(
            config.WINDOW_MIN_WIDTH,
            min(config.WINDOW_MAX_WIDTH, self.window_width + int(delta_w)),
        )
        self.window_height = max(
            config.WINDOW_MIN_HEIGHT,
            min(config.WINDOW_MAX_HEIGHT, self.window_height + int(delta_h)),
        )
        self.save()
        return self.window_width, self.window_height