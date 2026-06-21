"""Input binding map with persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import pygame

import config


class Action(str, Enum):
    ROTATE_LEFT = "rotate_left"
    ROTATE_RIGHT = "rotate_right"
    THRUST = "thrust"
    STRAFE_LEFT = "strafe_left"
    STRAFE_RIGHT = "strafe_right"
    FIRE = "fire"
    TOGGLE_AI_ARENA = "toggle_ai_arena"
    PAUSE = "pause"
    QUIT = "quit"


@dataclass(frozen=True)
class Binding:
    kind: str  # key | mouse_button | mouse_wheel
    code: int
    label: str


DEFAULT_BINDINGS: dict[Action, Binding] = {
    Action.ROTATE_LEFT: Binding("key", pygame.K_LEFT, "Left"),
    Action.ROTATE_RIGHT: Binding("key", pygame.K_RIGHT, "Right"),
    Action.THRUST: Binding("key", pygame.K_UP, "Up"),
    Action.STRAFE_LEFT: Binding("key", pygame.K_q, "Q"),
    Action.STRAFE_RIGHT: Binding("key", pygame.K_e, "E"),
    Action.FIRE: Binding("key", pygame.K_SPACE, "Space"),
    Action.TOGGLE_AI_ARENA: Binding("key", pygame.K_TAB, "Tab"),
    Action.PAUSE: Binding("key", pygame.K_p, "P"),
    Action.QUIT: Binding("key", pygame.K_F10, "F10"),
}

# Alternate defaults for WASD
WASD_ALIASES = {
    pygame.K_a: Action.ROTATE_LEFT,
    pygame.K_d: Action.ROTATE_RIGHT,
    pygame.K_w: Action.THRUST,
}

MOUSE_BUTTON_LABELS = {
    1: "Mouse Left",
    2: "Mouse Middle",
    3: "Mouse Right",
    4: "Mouse Side 1",
    5: "Mouse Side 2",
}

ACTION_LABELS = {
    Action.ROTATE_LEFT: "Rotate Left",
    Action.ROTATE_RIGHT: "Rotate Right",
    Action.THRUST: "Thrust",
    Action.STRAFE_LEFT: "Strafe Left",
    Action.STRAFE_RIGHT: "Strafe Right",
    Action.FIRE: "Fire",
    Action.TOGGLE_AI_ARENA: "Toggle AI Arena",
    Action.PAUSE: "Pause",
    Action.QUIT: "Quit",
}


def key_label(code: int) -> str:
    name = pygame.key.name(code)
    if name.startswith("kp"):
        return "NumPad " + name[2:].upper()
    return name.upper() if len(name) == 1 else name.capitalize()


@dataclass
class BindingMap:
    bindings: dict[Action, Binding] = field(default_factory=lambda: dict(DEFAULT_BINDINGS))
    path: Path = field(default_factory=lambda: Path(config.BINDINGS_FILE))

    def to_json(self) -> dict[str, Any]:
        return {
            action.value: {"kind": b.kind, "code": b.code, "label": b.label}
            for action, b in self.bindings.items()
        }

    @classmethod
    def from_json(cls, data: dict[str, Any], path: Path | None = None) -> BindingMap:
        bindings: dict[Action, Binding] = {}
        for action in Action:
            entry = data.get(action.value)
            if entry:
                bindings[action] = Binding(
                    entry["kind"], int(entry["code"]), entry.get("label", "?")
                )
            else:
                bindings[action] = DEFAULT_BINDINGS[action]
        return cls(bindings=bindings, path=path or Path(config.BINDINGS_FILE))

    def save(self) -> None:
        self.path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            loaded = self.from_json(data, self.path)
            self.bindings = loaded.bindings

    def restore_defaults(self) -> None:
        self.bindings = dict(DEFAULT_BINDINGS)

    def binding_key(self, binding: Binding) -> str:
        return f"{binding.kind}:{binding.code}"

    def set_binding(self, action: Action, binding: Binding) -> str | None:
        """Return error message if conflict."""
        new_key = self.binding_key(binding)
        for other_action, other in self.bindings.items():
            if other_action != action and self.binding_key(other) == new_key:
                return f"Already bound to {ACTION_LABELS[other_action]}"
        self.bindings[action] = binding
        return None

    def action_down(self, event: pygame.event.Event) -> Action | None:
        if event.type == pygame.KEYDOWN:
            for action, binding in self.bindings.items():
                if binding.kind == "key" and event.key == binding.code:
                    return action
            if event.key in WASD_ALIASES:
                return WASD_ALIASES[event.key]
        if event.type == pygame.MOUSEBUTTONDOWN:
            for action, binding in self.bindings.items():
                if binding.kind == "mouse_button" and event.button == binding.code:
                    return action
        if event.type == pygame.MOUSEWHEEL:
            code = 1 if event.y > 0 else -1
            for action, binding in self.bindings.items():
                if binding.kind == "mouse_wheel" and binding.code == code:
                    return action
        return None

    def action_held(self, keys: pygame.key.ScancodeWrapper, mouse_buttons: tuple[bool, ...]) -> set[Action]:
        active: set[Action] = set()
        for action, binding in self.bindings.items():
            if binding.kind == "key" and keys[binding.code]:
                active.add(action)
            elif binding.kind == "mouse_button" and binding.code - 1 < len(mouse_buttons):
                if mouse_buttons[binding.code - 1]:
                    active.add(action)
        for key, mapped in WASD_ALIASES.items():
            if keys[key]:
                active.add(mapped)
        return active

    def binding_from_event(self, event: pygame.event.Event) -> Binding | None:
        if event.type == pygame.KEYDOWN:
            return Binding("key", event.key, key_label(event.key))
        if event.type == pygame.MOUSEBUTTONDOWN:
            label = MOUSE_BUTTON_LABELS.get(event.button, f"Mouse {event.button}")
            return Binding("mouse_button", event.button, label)
        if event.type == pygame.MOUSEWHEEL:
            direction = 1 if event.y > 0 else -1
            label = "Wheel Up" if direction > 0 else "Wheel Down"
            return Binding("mouse_wheel", direction, label)
        return None