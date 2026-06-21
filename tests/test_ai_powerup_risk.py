"""AI power-up risk awareness in multi-ship melees."""

from ai import AIController
from combat import PowerUp, PowerUpKind
from ship import Ship, ShipVariant


def test_aborts_pickup_when_third_ship_near_loot() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    ship.angle = 0.0
    far = Ship.create(ShipVariant.LIGHT, (900.0, 300.0), ship_id=2)
    lurker = Ship.create(ShipVariant.HEAVY, (255.0, 330.0), ship_id=3)
    pu = PowerUp(PowerUpKind.FIRE_RATE, (240.0, 300.0))
    ctrl = AIController.for_ship(ship)
    _, _, _ = ctrl.update(ship, [ship, far, lurker], 0.05, [], [pu])
    assert ctrl.last_context.mode != "powerup"


def test_hurt_ship_still_grabs_close_shield_with_one_threat() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    ship.health = ship.max_health * 0.35
    ship.angle = 0.0
    enemy = Ship.create(ShipVariant.HEAVY, (360.0, 300.0), ship_id=2)
    pu = PowerUp(PowerUpKind.SHIELD, (250.0, 310.0))
    ctrl = AIController.for_ship(ship)
    _, thrust, _ = ctrl.update(ship, [ship, enemy], 0.05, [], [pu])
    assert ctrl.last_context.mode == "powerup"
    assert thrust <= 0.45