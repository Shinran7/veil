"""Persisted game settings (sound, etc.)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config


@dataclass
class GameSettings:
    sounds_enabled: bool = True
    path: Path = field(default_factory=lambda: Path(config.SETTINGS_FILE))

    def to_json(self) -> dict[str, Any]:
        return {"sounds_enabled": self.sounds_enabled}

    @classmethod
    def from_json(cls, data: dict[str, Any], path: Path | None = None) -> GameSettings:
        return cls(
            sounds_enabled=bool(data.get("sounds_enabled", True)),
            path=path or Path(config.SETTINGS_FILE),
        )

    def save(self) -> None:
        self.path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            loaded = self.from_json(data, self.path)
            self.sounds_enabled = loaded.sounds_enabled

    def toggle_sounds(self) -> bool:
        self.sounds_enabled = not self.sounds_enabled
        self.save()
        return self.sounds_enabled