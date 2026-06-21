"""Tests for controls module."""

import json
from pathlib import Path

from controls import Action, Binding, BindingMap, DEFAULT_BINDINGS


def test_restore_defaults() -> None:
    bm = BindingMap()
    bm.bindings[Action.FIRE] = Binding("key", 999, "test")
    bm.restore_defaults()
    assert bm.bindings[Action.FIRE].code == DEFAULT_BINDINGS[Action.FIRE].code


def test_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "bindings.json"
    bm = BindingMap(path=path)
    bm.save()
    bm2 = BindingMap(path=path)
    bm2.load()
    assert bm2.bindings[Action.THRUST].label == DEFAULT_BINDINGS[Action.THRUST].label


def test_binding_conflict() -> None:
    bm = BindingMap()
    fire_binding = bm.bindings[Action.FIRE]
    err = bm.set_binding(Action.THRUST, fire_binding)
    assert err is not None