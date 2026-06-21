"""Additional combat tests."""

from combat import (
    PowerUp,
    PowerUpKind,
    maybe_spawn_powerup,
    powerup_collected,
    powerup_sound_name,
    random_powerup_kind,
)
from ship import Ship, ShipVariant


def test_powerup_collected() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0))
    pu = PowerUp(PowerUpKind.SHIELD, (5.0, 0.0))
    assert powerup_collected(pu, ship)


def test_random_powerup_kind() -> None:
    assert random_powerup_kind() in PowerUpKind


def test_powerup_sound_names() -> None:
    assert powerup_sound_name(PowerUpKind.SHIELD) == "powerup_shield"
    assert powerup_sound_name(PowerUpKind.FIRE_RATE) == "powerup_fire_rate"
    assert powerup_sound_name(PowerUpKind.SPREAD) == "powerup_spread"


def test_maybe_spawn_powerup(monkeypatch) -> None:
    monkeypatch.setattr("combat.random.random", lambda: 0.0)
    pu = maybe_spawn_powerup((0.0, 0.0, 200.0, 200.0))
    assert pu is not None