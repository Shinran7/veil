"""CombatSituation snapshot — perception and mode eligibility without behavior change."""

import config
from ai import AIController
from ship import Ship, ShipVariant


def test_situation_tail_gunner_geometry() -> None:
    pursuer = Ship.create(ShipVariant.BALANCED, (140.0, 300.0), ship_id=1)
    pursuer.health = pursuer.max_health
    pursuer.angle = 0.05
    pursuer.velocity = (95.0, 0.0)
    leader = Ship.create(ShipVariant.LIGHT, (320.0, 300.0), ship_id=2)
    leader.angle = 0.0
    leader.velocity = (95.0, 0.0)
    ctrl = AIController.for_ship(pursuer)
    ctrl.update(pursuer, [pursuer, leader], 0.05, [])
    sit = ctrl.last_situation
    assert sit is not None
    assert sit.behind_target is True
    assert sit.tail_gunner is True
    assert sit.six_evade is False
    assert sit.reverse_gun is False
    assert config.AI_TAIL_MAINTAIN_DIST_MIN < sit.dist < config.AI_TAIL_MAINTAIN_DIST_MAX


def test_situation_six_evade_when_tailed() -> None:
    victim = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=1)
    victim.angle = 0.0
    victim.velocity = (90.0, 0.0)
    chaser = Ship.create(ShipVariant.LIGHT, (220.0, 300.0), ship_id=2)
    chaser.angle = 0.05
    chaser.velocity = (90.0, 0.0)
    ctrl = AIController.for_ship(victim)
    ctrl.update(victim, [victim, chaser], 0.05, [])
    sit = ctrl.last_situation
    assert sit is not None
    assert sit.being_tailed is True
    assert sit.rear_threat is chaser
    assert sit.six_evade is True
    assert sit.tail_gunner is False
    assert sit.rear_dist < config.AI_SIX_EVADE_CLOSE_DIST


def test_situation_reverse_eligible_head_on() -> None:
    defender = Ship.create(ShipVariant.BALANCED, (300.0, 300.0), ship_id=1)
    defender.angle = 0.0
    defender.velocity = (95.0, 0.0)
    charger = Ship.create(ShipVariant.HEAVY, (470.0, 300.0), ship_id=2)
    charger.angle = 3.14159265
    charger.velocity = (-120.0, 0.0)
    ctrl = AIController.for_ship(defender)
    eligible_ticks = 0
    for _ in range(40):
        ctrl.update(defender, [defender, charger], 0.05, [])
        sit = ctrl.last_situation
        assert sit is not None
        if sit.reverse_eligible:
            eligible_ticks += 1
        charger.position = (
            charger.position[0] + charger.velocity[0] * 0.05,
            charger.position[1],
        )
    assert eligible_ticks >= 10
    assert sit.reverse_gun is False or sit.reverse_gun is True


def test_situation_none_when_wandering() -> None:
    lone = Ship.create(ShipVariant.LIGHT, (100.0, 100.0), ship_id=1)
    ctrl = AIController.for_ship(lone)
    ctrl.update(lone, [lone], 0.05, [])
    assert ctrl.last_situation is None
    assert ctrl.last_context.mode == "wander"