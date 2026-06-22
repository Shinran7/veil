"""Asteroid cover — hide, ambush, and peek tactics."""

import math

import config
from ai import AIController, ARCHETYPE_PROFILES, CoverPhase, PilotArchetype
from arena import Obstacle
from ship import Ship, ShipVariant


def test_ship_in_cover_behind_asteroid() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (255.0, 200.0), ship_id=1)
    target = Ship.create(ShipVariant.LIGHT, (500.0, 200.0), ship_id=2)
    wall = Obstacle.blocking_at(300.0, 200.0, 45.0)
    ctrl = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.SURVIVOR])
    assert ctrl._ship_in_cover(ship, target, wall) is True


def test_hide_tactic_when_running_to_cover() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 200.0), ship_id=1)
    ship.angle = 0.0
    target = Ship.create(ShipVariant.LIGHT, (500.0, 200.0), ship_id=2)
    wall = Obstacle.blocking_at(300.0, 200.0, 45.0)
    ctrl = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.SURVIVOR])
    ctrl.update(ship, [ship, target], 0.05, [wall])
    assert ctrl.last_situation is not None
    assert ctrl.last_situation.active_tactic == "cover_hide"
    assert ctrl.last_context.mode == "cover_hide"


def test_ambush_after_holding_in_cover() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (255.0, 200.0), ship_id=1)
    ship.angle = math.pi
    target = Ship.create(ShipVariant.LIGHT, (500.0, 200.0), ship_id=2)
    target.velocity = (-100.0, 0.0)
    wall = Obstacle.blocking_at(300.0, 200.0, 45.0)
    ctrl = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.SURVIVOR])
    modes: list[str] = []
    for _ in range(100):
        ctrl.update(ship, [ship, target], 0.05, [wall])
        modes.append(ctrl.last_context.mode)
        target.position = (
            target.position[0] + target.velocity[0] * 0.05,
            target.position[1],
        )
    assert "cover_ambush" in modes


def test_peek_tactic_wins_when_burst_timer_active() -> None:
    from ai import TacticEvalContext, TacticId

    ship = Ship.create(ShipVariant.BALANCED, (255.0, 200.0), ship_id=1)
    target = Ship.create(ShipVariant.LIGHT, (500.0, 200.0), ship_id=2)
    wall = Obstacle.blocking_at(300.0, 200.0, 45.0)
    ctrl = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.SURVIVOR])
    ctrl.cover_peek_timer = config.AI_COVER_PEEK_COMMIT
    ctx = TacticEvalContext(
        ship=ship,
        target=target,
        opponents=[target],
        obstacles=[wall],
        arena_rect=None,
        rel_to_target=(245.0, 0.0),
        dist=245.0,
        closing=42.0,
        has_los=False,
        engage_quality=0.4,
        behind_target=False,
        shot_bearing=0.3,
        misaligned_shot=False,
        target_bearing=0.18,
        rear_threat=None,
        being_tailed=False,
        rear_dist=float("inf"),
        caution=0.12,
        shield_ramming=False,
        panic_pull=False,
        panicking=False,
        pickup=None,
        seeking_powerup=False,
        pickup_bias=0.0,
        six_close_dist=290.0,
        dt=0.05,
    )
    resolution = ctrl._resolve_tactics(ctx)
    assert resolution.active == TacticId.COVER_PEEK
    assert resolution.cover_phase == CoverPhase.PEEK