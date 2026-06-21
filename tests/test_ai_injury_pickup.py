"""AI injury slowdown and nearby pickup tests."""

from ai import AIController
from combat import PowerUp, PowerUpKind
from ship import Ship, ShipVariant


def test_hurt_ship_brakes_at_high_speed() -> None:
    ship = Ship.create(ShipVariant.LIGHT, (300.0, 300.0), ship_id=1)
    ship.health = ship.max_health * 0.3
    ship.velocity = (0.0, 320.0)
    enemy = Ship.create(ShipVariant.HEAVY, (700.0, 300.0), ship_id=2)
    ctrl = AIController.for_ship(ship)
    _, thrust, _ = ctrl.update(ship, [ship, enemy], 0.05, [])
    assert thrust < -0.4


def test_hurt_ship_grabs_nearby_shield_under_threat() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    ship.health = ship.max_health * 0.35
    ship.angle = 0.0
    enemy = Ship.create(ShipVariant.HEAVY, (320.0, 300.0), ship_id=2)
    pu = PowerUp(PowerUpKind.SHIELD, (250.0, 310.0))
    ctrl = AIController.for_ship(ship)
    _, thrust, _ = ctrl.update(ship, [ship, enemy], 0.05, [], [pu])
    assert ctrl.last_context.mode == "powerup"
    assert thrust <= 0.45