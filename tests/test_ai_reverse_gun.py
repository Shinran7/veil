"""Reverse gun run — committed astern fire when head-on and closing."""

import config
from ai import AIController
from ship import Ship, ShipVariant


def _head_on_close_setup() -> tuple[Ship, Ship, AIController]:
    defender = Ship.create(ShipVariant.BALANCED, (300.0, 300.0), ship_id=1)
    defender.angle = 0.0
    defender.velocity = (95.0, 0.0)
    charger = Ship.create(ShipVariant.HEAVY, (470.0, 300.0), ship_id=2)
    charger.angle = 3.14159265
    charger.velocity = (-120.0, 0.0)
    return defender, charger, AIController.for_ship(defender)


def test_reverse_gun_needs_eligibility_window() -> None:
    defender, charger, ctrl = _head_on_close_setup()
    modes: list[str] = []
    for _ in range(5):
        _, _, _ = ctrl.update(defender, [defender, charger], 0.05, [])
        modes.append(ctrl.last_context.mode)
        charger.position = (
            charger.position[0] + charger.velocity[0] * 0.05,
            charger.position[1],
        )
    assert "reverse_gun" not in modes


def test_reverse_gun_commits_after_sustained_head_on() -> None:
    defender, charger, ctrl = _head_on_close_setup()
    reverse_ticks = 0
    thrusts: list[float] = []
    for _ in range(80):
        _, thrust, _ = ctrl.update(defender, [defender, charger], 0.05, [])
        thrusts.append(thrust)
        if ctrl.last_context.mode == "reverse_gun":
            reverse_ticks += 1
        charger.position = (
            charger.position[0] + charger.velocity[0] * 0.05,
            charger.position[1],
        )
    assert reverse_ticks >= 8
    assert min(thrusts) <= config.AI_REVERSE_GUN_THRUST_MIN


def test_reverse_gun_ramps_not_instant_full_astern() -> None:
    defender, charger, ctrl = _head_on_close_setup()
    defender.velocity = (180.0, 0.0)
    first_reverse: float | None = None
    for _ in range(90):
        _, thrust, _ = ctrl.update(defender, [defender, charger], 0.05, [])
        if ctrl.last_context.mode == "reverse_gun" and first_reverse is None:
            first_reverse = thrust
            break
        charger.position = (
            charger.position[0] + charger.velocity[0] * 0.05,
            charger.position[1],
        )
    assert first_reverse is not None
    assert first_reverse > config.AI_REVERSE_GUN_THRUST_MAX


def test_tail_position_does_not_reverse_gun() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (140.0, 300.0), ship_id=1)
    pursuer.angle = 0.05
    pursuer.velocity = (95.0, 0.0)
    leader = Ship.create(ShipVariant.LIGHT, (320.0, 300.0), ship_id=2)
    leader.angle = 0.0
    leader.velocity = (95.0, 0.0)
    ctrl = AIController.for_ship(pursuer)
    for _ in range(80):
        _, _, _ = ctrl.update(pursuer, [pursuer, leader], 0.05, [])
        assert ctrl.last_context.mode != "reverse_gun"