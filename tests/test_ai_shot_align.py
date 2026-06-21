"""AI should turn toward a tail target instead of kiting sideways."""

import math

from ai import AIController
from ship import Ship, ShipVariant


def test_behind_misaligned_hurtish_ship_aligns_not_kites() -> None:
    """Above tail-gunner health floor but still injured — was kiting sideways."""
    ship = Ship.create(ShipVariant.LIGHT, (130.0, 300.0), ship_id=1)
    ship.health = ship.max_health * 0.55
    ship.angle = 2.3
    heavy = Ship.create(ShipVariant.HEAVY, (300.0, 300.0), ship_id=2)
    heavy.angle = 0.0
    heavy.velocity = (60.0, 0.0)
    ctrl = AIController.for_ship(ship)
    rel = ctrl._target_delta(ship, heavy, None)
    to_target = math.atan2(rel[1], rel[0])
    diff = ctrl._angle_diff(ship.angle, to_target)
    rot, _, _ = ctrl.update(ship, [ship, heavy], 0.05, [])
    assert ctrl.last_context.mode == "tail_gunner"
    assert ctrl.last_context.kiting is False
    if diff > 0.15:
        assert rot > 0
    elif diff < -0.15:
        assert rot < 0


def test_behind_misaligned_bearing_improves_over_time() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (130.0, 300.0), ship_id=1)
    ship.health = ship.max_health * 0.55
    ship.angle = 2.4
    enemy = Ship.create(ShipVariant.LIGHT, (300.0, 300.0), ship_id=2)
    enemy.angle = 0.0
    enemy.velocity = (90.0, 0.0)
    ctrl = AIController.for_ship(ship)
    start_bearing = ctrl._shot_alignment_bearing(
        ship, enemy, ctrl._target_delta(ship, enemy, None)
    )
    for _ in range(90):
        rot, _, _ = ctrl.update(ship, [ship, enemy], 0.05, [])
        ship.apply_rotation(rot, 0.05)
        ship.apply_thrust(0, 0.05 * ctrl.last_context.thrust)
        enemy.position = (
            enemy.position[0] + enemy.velocity[0] * 0.05,
            enemy.position[1],
        )
    end_bearing = ctrl._shot_alignment_bearing(
        ship, enemy, ctrl._target_delta(ship, enemy, None)
    )
    assert end_bearing < start_bearing - 0.25