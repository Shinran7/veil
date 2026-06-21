"""AI power-up seeking tests."""

from ai import AIController
from combat import PowerUp, PowerUpKind
from ship import Ship, ShipVariant


def test_safe_powerup_scores_high() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    pu = PowerUp(PowerUpKind.SHIELD, (280.0, 300.0))
    ctrl = AIController.for_ship(ship)
    score = ctrl._powerup_seek_score(ship, pu, 80.0, 420.0, 0.1, [])
    assert score >= 0.5


def test_ai_grabs_safe_nearby_powerup() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    ship.angle = 0.0
    enemy = Ship.create(ShipVariant.LIGHT, (760.0, 300.0), ship_id=2)
    pu = PowerUp(PowerUpKind.SHIELD, (310.0, 300.0))
    ctrl = AIController.for_ship(ship)
    _, thrust, _ = ctrl.update(ship, [ship, enemy], 0.05, [], [pu])
    assert ctrl.last_context.mode == "powerup"
    assert thrust >= 0.3


def test_ai_skips_risky_close_powerup() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=1)
    enemy = Ship.create(ShipVariant.LIGHT, (255.0, 300.0), ship_id=2)
    pu = PowerUp(PowerUpKind.FIRE_RATE, (230.0, 300.0))
    ctrl = AIController.for_ship(ship)
    pickup = ctrl._best_powerup_target(ship, [pu], 55.0, 0.2, [])
    assert pickup is None or pickup[2] < 0.5