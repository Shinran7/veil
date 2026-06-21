"""Tests for AI module."""

from ai import AIController, Personality
from ship import Ship, ShipVariant


def test_nearest_threat() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    near = Ship.create(ShipVariant.LIGHT, (50.0, 0.0), ship_id=2)
    far = Ship.create(ShipVariant.HEAVY, (500.0, 0.0), ship_id=3)
    ctrl = AIController(Personality.AGGRESSIVE)
    target = ctrl.nearest_threat(ship, [ship, near, far])
    assert target is near


def test_ai_update_returns_controls() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    enemy = Ship.create(ShipVariant.LIGHT, (420.0, 0.0), ship_id=2)
    ctrl = AIController(Personality.AGGRESSIVE)
    rot, thrust, fire = ctrl.update(ship, [ship, enemy], 0.016)
    assert thrust >= 0