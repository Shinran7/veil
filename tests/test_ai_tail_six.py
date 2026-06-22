"""Tail-gunner hold and six-o'clock evasion."""

import math

from ai import AIController
from ship import Ship, ShipVariant


def test_healthy_aligned_ship_holds_tail() -> None:
    """Full-health pursuer on the six should stay in tail_gunner, not fight/strafe off."""
    pursuer = Ship.create(ShipVariant.BALANCED, (140.0, 300.0), ship_id=1)
    pursuer.health = pursuer.max_health
    pursuer.angle = 0.05
    pursuer.velocity = (95.0, 0.0)
    leader = Ship.create(ShipVariant.LIGHT, (320.0, 300.0), ship_id=2)
    leader.angle = 0.0
    leader.velocity = (95.0, 0.0)
    ctrl = AIController.for_ship(pursuer)
    _, _, _ = ctrl.update(pursuer, [pursuer, leader], 0.05, [])
    assert ctrl.last_context.tail_gunner is True
    assert ctrl.last_context.mode == "tail_gunner"
    assert ctrl.last_context.kiting is False
    assert ctrl.last_context.breaking_orbit is False


def test_tail_gunner_prefers_locked_target() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (140.0, 300.0), ship_id=1)
    pursuer.angle = 0.1
    leader = Ship.create(ShipVariant.LIGHT, (320.0, 300.0), ship_id=2)
    leader.angle = 0.0
    leader.velocity = (80.0, 0.0)
    closer = Ship.create(ShipVariant.LIGHT, (200.0, 360.0), ship_id=3)
    closer.angle = -1.2
    ctrl = AIController.for_ship(pursuer)
    ctrl.locked_target_id = leader.ship_id
    _, _, _ = ctrl.update(pursuer, [pursuer, leader, closer], 0.05, [])
    assert ctrl.last_context.target_id == leader.ship_id


def test_being_tailed_triggers_six_evade() -> None:
    victim = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=1)
    victim.angle = 0.0
    victim.velocity = (90.0, 0.0)
    chaser = Ship.create(ShipVariant.LIGHT, (220.0, 300.0), ship_id=2)
    chaser.angle = 0.05
    chaser.velocity = (90.0, 0.0)
    ctrl = AIController.for_ship(victim)
    _, thrust, _ = ctrl.update(victim, [victim, chaser], 0.05, [])
    assert ctrl.last_context.being_tailed is True
    assert ctrl.last_context.six_evade is True
    assert ctrl.last_context.mode == "six_evade"
    assert thrust >= 0.5
    assert abs(ctrl.last_context.caution) > 0.2


def test_six_evade_aims_off_chaser_line() -> None:
    victim = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=1)
    victim.angle = math.pi
    chaser = Ship.create(ShipVariant.LIGHT, (240.0, 300.0), ship_id=2)
    chaser.angle = 0.0
    ctrl = AIController.for_ship(victim)
    aim = ctrl._break_six_aim(victim, chaser, None)
    rel = (aim[0] - victim.position[0], aim[1] - victim.position[1])
    to_chaser = math.atan2(
        chaser.position[1] - victim.position[1],
        chaser.position[0] - victim.position[0],
    )
    break_bearing = math.atan2(rel[1], rel[0])
    assert abs(ctrl._angle_diff(to_chaser, break_bearing)) > 0.35