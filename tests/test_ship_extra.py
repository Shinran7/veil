"""Additional ship tests."""

from ship import Ship, ShipVariant
from utils import wrap_position


def test_hull_points() -> None:
    ship = Ship.create(ShipVariant.HEAVY, (100.0, 50.0), angle=0.0)
    pts = ship.hull_points()
    assert len(pts) == len(ship.hull_points())
    assert all(isinstance(p[0], float) for p in pts)


def test_wrap_left_to_right() -> None:
    rect = (0.0, 0.0, 200.0, 200.0)
    ship = Ship.create(ShipVariant.LIGHT, (-5.0, 100.0))
    ship.velocity = (-400.0, 0.0)
    ship.update_physics(0.1, rect)
    assert ship.position[0] > 150.0


def test_wrap_bottom_to_top() -> None:
    rect = (0.0, 0.0, 200.0, 200.0)
    wrapped = wrap_position((100.0, 205.0), rect)
    assert wrapped[1] == 5.0


def test_fire_rate_powerup() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0))
    ship.apply_powerup("fire_rate")
    assert ship.fire_rate_timer > 0
    assert ship.effective_fire_cooldown() < 0.3