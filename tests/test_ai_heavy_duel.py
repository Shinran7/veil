"""Heavy vs heavy 1v1 should close and fight, not meander at long range."""

import math

from ai import AIController
from ship import Ship, ShipVariant

ARENA = (0.0, 0.0, 1200.0, 600.0)


def _simulate_heavy_duel(start_dist: float, steps: int = 1800) -> tuple[float, int, str]:
    a = Ship.create(ShipVariant.HEAVY, (400.0, 300.0), ship_id=1)
    a.angle = 0.0
    b = Ship.create(ShipVariant.HEAVY, (400.0 + start_dist, 300.0), ship_id=2)
    b.angle = math.pi
    ca = AIController.for_ship(a)
    cb = AIController.for_ship(b)
    fires = 0
    for _ in range(steps):
        for ship, ctrl in ((a, ca), (b, cb)):
            rot, thrust, fire = ctrl.update(ship, [a, b], 0.05, [], [], ARENA)
            fires += int(fire)
            ship.apply_rotation(rot, 0.05)
            if thrust:
                ship.apply_thrust(0, 0.05 * thrust)
        for ship in (a, b):
            ship.update_physics(0.05, ARENA)
    end_dist = math.hypot(b.position[0] - a.position[0], b.position[1] - a.position[1])
    return end_dist, fires, ca.last_context.mode


def test_heavy_duel_uses_dedicated_mode() -> None:
    a = Ship.create(ShipVariant.HEAVY, (200.0, 300.0), ship_id=1)
    b = Ship.create(ShipVariant.HEAVY, (620.0, 300.0), ship_id=2)
    ctrl = AIController.for_ship(a)
    _, _, _ = ctrl.update(a, [a, b], 0.05, [], [], ARENA)
    assert ctrl.last_context.mode == "heavy_duel"
    assert ctrl.last_context.heavy_duel is True


def test_heavy_duel_closes_from_long_range() -> None:
    end_dist, fires, mode = _simulate_heavy_duel(620.0, steps=1500)
    assert mode in ("heavy_duel", "tail_gunner", "fight")
    assert end_dist < 520.0
    assert fires >= 200


def test_heavy_duel_enters_weapon_range_from_mid_distance() -> None:
    a = Ship.create(ShipVariant.HEAVY, (400.0, 300.0), ship_id=1)
    a.angle = 0.0
    b = Ship.create(ShipVariant.HEAVY, (820.0, 300.0), ship_id=2)
    b.angle = math.pi
    ca = AIController.for_ship(a)
    cb = AIController.for_ship(b)
    min_dist = float("inf")
    for _ in range(1500):
        for ship, ctrl in ((a, ca), (b, cb)):
            rot, thrust, _ = ctrl.update(ship, [a, b], 0.05, [], [], ARENA)
            ship.apply_rotation(rot, 0.05)
            if thrust:
                ship.apply_thrust(0, 0.05 * thrust)
        for ship in (a, b):
            ship.update_physics(0.05, ARENA)
        min_dist = min(
            min_dist,
            math.hypot(b.position[0] - a.position[0], b.position[1] - a.position[1]),
        )
    assert min_dist < 360.0


def test_heavy_duel_commit_after_stale_standoff() -> None:
    a = Ship.create(ShipVariant.HEAVY, (200.0, 300.0), ship_id=1)
    b = Ship.create(ShipVariant.HEAVY, (655.0, 300.0), ship_id=2)
    ctrl = AIController.for_ship(a)
    ctrl.heavy_duel_stale_timer = 2.1
    _, thrust, _ = ctrl.update(a, [a, b], 0.05, [], [], ARENA)
    assert ctrl.heavy_duel_commit_timer > 0.0
    assert thrust >= 0.8