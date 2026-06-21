"""High score persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import config


@dataclass
class HighScoreEntry:
    score: int
    wave: int
    ship: str


@dataclass
class HighScoreTable:
    entries: list[HighScoreEntry] = field(default_factory=list)
    path: Path = field(default_factory=lambda: Path(config.HIGH_SCORE_FILE))
    max_entries: int = 10

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.entries = [
            HighScoreEntry(e["score"], e["wave"], e["ship"]) for e in data.get("entries", [])
        ]

    def save(self) -> None:
        payload = {
            "entries": [
                {"score": e.score, "wave": e.wave, "ship": e.ship}
                for e in self.entries
            ]
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, score: int, wave: int, ship: str) -> bool:
        """Return True if this score made the table."""
        self.entries.append(HighScoreEntry(score, wave, ship))
        self.entries.sort(key=lambda e: e.score, reverse=True)
        made = any(e.score == score and e.wave == wave for e in self.entries[: self.max_entries])
        self.entries = self.entries[: self.max_entries]
        self.save()
        return made