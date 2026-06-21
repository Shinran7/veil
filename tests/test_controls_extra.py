"""Additional controls tests."""

import pygame

from controls import Action, Binding, BindingMap, key_label


def test_key_label_numpad() -> None:
    assert "NumPad" in key_label(pygame.K_KP8) or "kp" not in pygame.key.name(pygame.K_KP8)


def test_binding_key_format() -> None:
    bm = BindingMap()
    b = Binding("mouse_wheel", 1, "Wheel Up")
    assert bm.binding_key(b) == "mouse_wheel:1"


def test_from_json_partial() -> None:
    data = {"fire": {"kind": "key", "code": 32, "label": "Space"}}
    bm = BindingMap.from_json(data)
    assert bm.bindings[Action.FIRE].code == 32