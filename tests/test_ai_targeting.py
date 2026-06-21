"""AI opportunistic targeting and 1v1 engagement tests."""

import math

from ai import AIController, Personality
from ship import Ship, ShipVariant


def test_prefers_lined_up_target_over_closer_off_boresight() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    ship.angle = 0.0
    easy = Ship.create(ShipVariant.LIGHT, (220.0, 0.0), ship_id=2)
    easy.health = easy.max_health * 0.25
    closer = Ship.create(ShipVariant.HEAVY, (70.0, 120.0), ship_id=3)
    ctrl = AIController(Personality.AGGRESSIVE)
    target = ctrl._select_combat_target(ship, [ship, easy, closer], [])
    assert target is easy


def test_target_lock_hysteresis_avoids_flicker() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    ship.angle = 0.0
    a = Ship.create(ShipVariant.LIGHT, (200.0, 0.0), ship_id=2)
    b = Ship.create(ShipVariant.LIGHT, (205.0, 15.0), ship_id=3)
    ctrl = AIController(Personality.AGGRESSIVE)
    first = ctrl._select_combat_target(ship, [ship, a, b], [])
    second = ctrl._select_combat_target(ship, [ship, a, b], [])
    assert first is not None
    assert second.ship_id == first.ship_id


def test_solo_dogfight_caps_thrust_when_well_positioned() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    ship.angle = 0.0
    ship.velocity = (40.0, 0.0)
    enemy = Ship.create(ShipVariant.BALANCED, (430.0, 300.0), ship_id=2)
    enemy.angle = math.pi
    enemy.velocity = (-40.0, 0.0)
    ctrl = AIController.for_ship(ship)
    _, thrust, _ = ctrl.update(ship, [ship, enemy], 0.05, [])
    assert ctrl.last_context.engage_quality >= 0.4
    assert thrust <= 0.35