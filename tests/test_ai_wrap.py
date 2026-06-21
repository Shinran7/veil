"""AI toroidal map awareness tests."""

from ai import AIController
from ship import Ship, ShipVariant

ARENA = (0.0, 0.0, 800.0, 600.0)


def test_nearest_threat_uses_wrapped_distance() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (400.0, 20.0), ship_id=1)
    near = Ship.create(ShipVariant.LIGHT, (500.0, 300.0), ship_id=2)
    wrapped = Ship.create(ShipVariant.HEAVY, (400.0, 580.0), ship_id=3)
    ctrl = AIController.for_ship(ship)
    target = ctrl.nearest_threat(ship, [ship, near, wrapped], ARENA)
    assert target is wrapped


def test_hurt_ship_fires_when_behind_target() -> None:
    hurt = Ship.create(ShipVariant.BALANCED, (120.0, 300.0), ship_id=4)
    hurt.health = hurt.max_health * 0.2
    hurt.angle = 0.0
    enemy = Ship.create(ShipVariant.HEAVY, (300.0, 300.0), ship_id=5)
    enemy.angle = 0.0
    ctrl = AIController.for_ship(hurt)
    fired = False
    for _ in range(30):
        _, _, fire = ctrl.update(hurt, [hurt, enemy], 0.05, [], [], ARENA)
        fired = fired or fire
    assert fired