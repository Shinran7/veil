"""Persisted game settings (volume, etc.)."""

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
    path: Path = field(default_factory=lambda: Path(config.SETTINGS_FILE))

    def to_json(self) -> dict[str, Any]:
        return {
            "sfx_volume": self.sfx_volume,
            "music_volume": self.music_volume,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any], path: Path | None = None) -> GameSettings:
        sfx, music = cls._parse_volumes(data)
        return cls(sfx_volume=sfx, music_volume=music, path=path or Path(config.SETTINGS_FILE))

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

    def adjust_sfx_volume(self, delta: float) -> float:
        self.sfx_volume = _clamp_volume(self.sfx_volume + delta)
        self.save()
        return self.sfx_volume

    def adjust_music_volume(self, delta: float) -> float:
        self.music_volume = _clamp_volume(self.music_volume + delta)
        self.save()
        return self.music_volume