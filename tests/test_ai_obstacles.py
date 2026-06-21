"""AI obstacle navigation tests."""

from ai import AIController, Personality
from arena import Obstacle
from ship import Ship, ShipVariant


def test_ai_does_not_fire_through_obstacle() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 200.0), ship_id=1)
    ship.angle = 0.0
    target = Ship.create(ShipVariant.LIGHT, (400.0, 200.0), ship_id=2)
    wall = Obstacle.blocking_at(260.0, 200.0, 40.0)
    ctrl = AIController(Personality.AGGRESSIVE)
    _, _, fire = ctrl.update(ship, [ship, target], 0.016, [wall])
    assert fire is False


def test_ai_flanks_when_path_blocked() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 200.0), ship_id=1)
    target = Ship.create(ShipVariant.LIGHT, (500.0, 200.0), ship_id=2)
    wall = Obstacle.blocking_at(300.0, 200.0, 45.0)
    ctrl = AIController(Personality.AGGRESSIVE)
    rot, thrust, _ = ctrl.update(ship, [ship, target], 0.016, [wall])
    assert thrust > 0
    assert rot != 0 or thrust > 0.5