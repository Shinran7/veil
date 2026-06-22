"""Scored tactic modules — priority selection and profile weighting."""

from ai import (
    AIController,
    ARCHETYPE_PROFILES,
    NEUTRAL_PROFILE,
    PilotArchetype,
    TacticId,
    TacticEvalContext,
)
from arena import Obstacle
from ship import Ship, ShipVariant


def _base_ctx(
    ship: Ship,
    target: Ship,
    *,
    behind: bool = False,
    tailed: bool = False,
    has_los: bool = True,
    obstacles: list | None = None,
) -> TacticEvalContext:
    return TacticEvalContext(
        ship=ship,
        target=target,
        opponents=[target],
        obstacles=obstacles or [],
        arena_rect=None,
        rel_to_target=(220.0, 0.0),
        dist=220.0,
        closing=-40.0,
        has_los=has_los,
        engage_quality=0.62,
        behind_target=behind,
        shot_bearing=0.2,
        misaligned_shot=False,
        target_bearing=0.15,
        rear_threat=target if tailed else None,
        being_tailed=tailed,
        rear_dist=180.0 if tailed else float("inf"),
        caution=0.15,
        shield_ramming=False,
        panic_pull=False,
        panicking=False,
        pickup=None,
        seeking_powerup=False,
        pickup_bias=0.0,
        six_close_dist=290.0,
        dt=0.05,
    )


def test_pick_tactic_prefers_tail_over_fight() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (100.0, 300.0), ship_id=1)
    leader = Ship.create(ShipVariant.LIGHT, (320.0, 300.0), ship_id=2)
    ctrl = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.HUNTER])
    ctx = _base_ctx(pursuer, leader, behind=True)
    resolution = ctrl._resolve_tactics(ctx)
    assert resolution.active == TacticId.TAIL_GUNNER
    assert resolution.tail_gunner is True
    assert any(s.tactic == TacticId.TAIL_GUNNER and s.score > 0 for s in resolution.scores)


def test_cover_scores_when_los_blocked_near_rock() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 200.0), ship_id=1)
    target = Ship.create(ShipVariant.LIGHT, (500.0, 200.0), ship_id=2)
    wall = Obstacle.blocking_at(300.0, 200.0, 45.0)
    survivor = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.SURVIVOR])
    ctx = _base_ctx(ship, target, has_los=False, obstacles=[wall])
    cover_score = survivor._score_cover(ctx)
    assert cover_score >= 0.55


def test_active_tactic_on_situation_matches_context_mode() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (140.0, 300.0), ship_id=1)
    pursuer.health = pursuer.max_health
    pursuer.angle = 0.05
    pursuer.velocity = (95.0, 0.0)
    leader = Ship.create(ShipVariant.LIGHT, (320.0, 300.0), ship_id=2)
    leader.angle = 0.0
    leader.velocity = (95.0, 0.0)
    ctrl = AIController(profile=NEUTRAL_PROFILE)
    ctrl.update(pursuer, [pursuer, leader], 0.05, [])
    assert ctrl.last_situation is not None
    assert ctrl.last_situation.active_tactic == "tail_gunner"
    assert ctrl.last_context.mode == "tail_gunner"
    assert ctrl.last_active_tactic == TacticId.TAIL_GUNNER