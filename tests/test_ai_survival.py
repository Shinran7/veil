"""AI survival / retreat behavior tests."""

import math

from ai import AIController, Personality
from ship import Ship, ShipVariant


def test_shielded_ship_rams_instead_of_fleeing() -> None:
    light = Ship.create(ShipVariant.LIGHT, (300.0, 300.0), ship_id=2)
    light.shield_timer = 6.0
    light.angle = 0.0
    light.velocity = (140.0, 0.0)
    heavy = Ship.create(ShipVariant.HEAVY, (420.0, 300.0), ship_id=3)
    ctrl = AIController.for_ship(light)
    _, thrust, _ = ctrl.update(light, [light, heavy], 0.05, [])
    assert thrust >= 0.9


def test_light_retreats_from_close_heavy() -> None:
    light = Ship.create(ShipVariant.LIGHT, (300.0, 300.0), ship_id=2)
    light.health = light.max_health * 0.32
    light.angle = 0.0
    light.velocity = (140.0, 0.0)
    heavy = Ship.create(ShipVariant.HEAVY, (420.0, 300.0), ship_id=3)
    ctrl = AIController.for_ship(light)
    _, thrust, _ = ctrl.update(light, [light, heavy], 0.05, [])
    assert thrust < 0.0


def test_hurt_medium_kites_heavy_instead_of_pure_reverse() -> None:
    medium = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=4)
    medium.health = medium.max_health * 0.22
    medium.angle = 0.0
    medium.velocity = (60.0, 0.0)
    heavy = Ship.create(ShipVariant.HEAVY, (430.0, 300.0), ship_id=5)
    ctrl = AIController.for_ship(medium)
    thrusts: list[float] = []
    for _ in range(60):
        _, thrust, _ = ctrl.update(medium, [medium, heavy], 0.05, [])
        thrusts.append(thrust)
    assert max(thrusts) >= 0.35
    assert min(thrusts) >= -0.55


def test_hurt_ship_reengages_when_far_away() -> None:
    hurt = Ship.create(ShipVariant.BALANCED, (100.0, 300.0), ship_id=10)
    hurt.health = hurt.max_health * 0.2
    hurt.angle = math.pi
    hurt.velocity = (-180.0, 0.0)
    enemy = Ship.create(ShipVariant.HEAVY, (900.0, 300.0), ship_id=11)
    ctrl = AIController.for_ship(hurt)
    thrusts: list[float] = []
    for _ in range(50):
        _, thrust, _ = ctrl.update(hurt, [hurt, enemy], 0.05, [])
        thrusts.append(thrust)
    assert min(thrusts) >= -0.55
    assert max(thrusts) >= 0.15


def test_hurt_medium_can_fire_while_kiting_heavy() -> None:
    medium = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=6)
    medium.health = medium.max_health * 0.22
    medium.angle = 0.0
    heavy = Ship.create(ShipVariant.HEAVY, (430.0, 300.0), ship_id=7)
    ctrl = AIController.for_ship(medium)
    ctrl.kite_burst_timer = 0.5
    fired = False
    for _ in range(40):
        _, _, fire = ctrl.update(medium, [medium, heavy], 0.05, [])
        fired = fired or fire
    assert fired


def test_hurt_ship_at_range_kites_not_panics() -> None:
    medium = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=12)
    medium.health = medium.max_health * 0.2
    medium.angle = 0.0
    heavy = Ship.create(ShipVariant.HEAVY, (480.0, 300.0), ship_id=13)
    ctrl = AIController.for_ship(medium)
    _, _, _ = ctrl.update(medium, [medium, heavy], 0.05, [])
    assert ctrl.last_context.mode in ("kite", "tail_gunner", "fight")
    assert ctrl.last_context.mode != "panic"


def test_hurt_ship_does_not_spin_to_shoot() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=8)
    ship.health = ship.max_health * 0.18
    ship.angle = 2.8
    enemy = Ship.create(ShipVariant.LIGHT, (360.0, 300.0), ship_id=9)
    ctrl = AIController(Personality.AGGRESSIVE)
    fired = False
    for _ in range(40):
        _, _, fire = ctrl.update(ship, [ship, enemy], 0.05, [])
        fired = fired or fire
    assert not fired