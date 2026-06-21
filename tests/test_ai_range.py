"""AI range-aware dogfight tests."""

import math

from ai import AIController
from ship import Ship, ShipVariant


def test_healthy_light_closes_at_distance() -> None:
    light = Ship.create(ShipVariant.LIGHT, (100.0, 300.0), ship_id=1)
    light.angle = 0.0
    heavy = Ship.create(ShipVariant.HEAVY, (500.0, 300.0), ship_id=2)
    ctrl = AIController.for_ship(light)
    thrusts: list[float] = []
    for _ in range(30):
        _, thrust, _ = ctrl.update(light, [light, heavy], 0.05, [])
        thrusts.append(thrust)
    assert max(thrusts) >= 0.55


def test_heavy_opens_when_light_is_close() -> None:
    heavy = Ship.create(ShipVariant.HEAVY, (400.0, 300.0), ship_id=3)
    heavy.angle = math.pi
    light = Ship.create(ShipVariant.LIGHT, (250.0, 300.0), ship_id=4)
    light.velocity = (80.0, 0.0)
    ctrl = AIController.for_ship(heavy)
    thrusts: list[float] = []
    for _ in range(30):
        _, thrust, _ = ctrl.update(heavy, [heavy, light], 0.05, [])
        thrusts.append(thrust)
    assert min(thrusts) <= 0.25


def test_hurt_light_still_retreats_from_close_heavy() -> None:
    light = Ship.create(ShipVariant.LIGHT, (300.0, 300.0), ship_id=5)
    light.health = light.max_health * 0.3
    light.angle = 0.0
    light.velocity = (140.0, 0.0)
    heavy = Ship.create(ShipVariant.HEAVY, (420.0, 300.0), ship_id=6)
    ctrl = AIController.for_ship(light)
    _, thrust, _ = ctrl.update(light, [light, heavy], 0.05, [])
    assert thrust < 0.0