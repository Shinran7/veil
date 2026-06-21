"""AI orbit-break behavior tests."""

from ai import AIController, Personality
from ship import Ship, ShipVariant


def test_stale_tail_chase_triggers_break() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (180.0, 300.0), ship_id=1)
    pursuer.angle = 0.9
    pursuer.velocity = (110.0, 0.0)
    leader = Ship.create(ShipVariant.LIGHT, (360.0, 300.0), ship_id=2)
    leader.angle = 0.0
    leader.velocity = (110.0, 0.0)
    ctrl = AIController(Personality.AGGRESSIVE)
    thrusts: list[float] = []
    for _ in range(90):
        _, thrust, _ = ctrl.update(pursuer, [pursuer, leader], 0.05, [])
        thrusts.append(thrust)
    assert min(thrusts) < 0.5


def test_mutual_orbit_detected() -> None:
    a = Ship.create(ShipVariant.BALANCED, (400.0, 250.0), ship_id=2)
    a.angle = 1.57
    a.velocity = (0.0, 95.0)
    b = Ship.create(ShipVariant.BALANCED, (600.0, 250.0), ship_id=3)
    b.angle = -1.57
    b.velocity = (0.0, -95.0)
    ctrl = AIController.for_ship(a)
    ctrl.last_dist = 200.0
    assert ctrl._is_mutual_orbit(a, b, 200.0, 0.0)


def test_orbit_break_force_shot_after_stale_circle() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=2)
    pursuer.angle = 1.2
    pursuer.velocity = (0.0, 90.0)
    leader = Ship.create(ShipVariant.LIGHT, (560.0, 300.0), ship_id=3)
    leader.angle = -1.2
    leader.velocity = (0.0, -90.0)
    ctrl = AIController.for_ship(pursuer)
    ctrl.last_dist = 160.0
    ctrl.orbit_stale_timer = 0.5
    ctrl.orbit_break_timer = 0.26
    pursuer.weapon_cooldown = 0.0
    fired = False
    for _ in range(50):
        _, _, shoot = ctrl.update(pursuer, [pursuer, leader], 0.05, [])
        fired = fired or shoot
    assert fired


def test_orbit_break_fires_when_in_range() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=2)
    pursuer.angle = 0.0
    pursuer.velocity = (0.0, 90.0)
    leader = Ship.create(ShipVariant.LIGHT, (560.0, 300.0), ship_id=3)
    leader.angle = 3.14
    leader.velocity = (0.0, -90.0)
    ctrl = AIController.for_ship(pursuer)
    ctrl.last_dist = 160.0
    fired = False
    for _ in range(40):
        _, _, shoot = ctrl.update(pursuer, [pursuer, leader], 0.05, [])
        fired = fired or shoot
    assert fired


def test_mutual_orbit_triggers_break() -> None:
    a = Ship.create(ShipVariant.BALANCED, (400.0, 250.0), ship_id=2)
    a.angle = 1.57
    a.velocity = (0.0, 95.0)
    b = Ship.create(ShipVariant.BALANCED, (600.0, 250.0), ship_id=3)
    b.angle = -1.57
    b.velocity = (0.0, -95.0)
    ctrl = AIController.for_ship(a)
    ctrl.last_dist = 200.0
    thrusts: list[float] = []
    for _ in range(24):
        _, thrust, _ = ctrl.update(a, [a, b], 0.05, [])
        thrusts.append(thrust)
    assert min(thrusts) <= -0.4 or max(thrusts) >= 0.1