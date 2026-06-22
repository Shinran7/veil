"""Pilot profiles — archetype assignment and tendency weight hooks."""

import config
from ai import (
    AIController,
    ARCHETYPE_PROFILES,
    NEUTRAL_PROFILE,
    PilotArchetype,
    profile_for_ship,
)
from combat import PowerUp, PowerUpKind
from ship import Ship, ShipVariant


def test_profile_for_ship_maps_variant_and_id() -> None:
    light_hunter = profile_for_ship(
        Ship.create(ShipVariant.LIGHT, (0.0, 0.0), ship_id=4)
    )
    heavy_survivor = profile_for_ship(
        Ship.create(ShipVariant.HEAVY, (0.0, 0.0), ship_id=1)
    )
    assert light_hunter.archetype == PilotArchetype.HUNTER
    assert heavy_survivor.archetype == PilotArchetype.SURVIVOR


def test_for_ship_exposes_archetype_in_context() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 300.0), ship_id=2)
    ctrl = AIController.for_ship(ship)
    enemy = Ship.create(ShipVariant.LIGHT, (500.0, 300.0), ship_id=9)
    ctrl.update(ship, [ship, enemy], 0.05, [])
    assert ctrl.profile.archetype == PilotArchetype.FLANKER
    assert ctrl.last_context.archetype == "flanker"


def test_survivor_six_evade_at_longer_rear_range() -> None:
    victim = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=1)
    victim.angle = 0.0
    victim.velocity = (90.0, 0.0)
    chaser = Ship.create(ShipVariant.LIGHT, (100.0, 300.0), ship_id=2)
    chaser.angle = 0.05
    chaser.velocity = (90.0, 0.0)
    survivor = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.SURVIVOR])
    neutral = AIController(profile=NEUTRAL_PROFILE)
    survivor.update(victim, [victim, chaser], 0.05, [])
    neutral.update(victim, [victim, chaser], 0.05, [])
    assert survivor.last_situation is not None
    assert neutral.last_situation is not None
    assert survivor.last_situation.rear_dist > config.AI_SIX_EVADE_CLOSE_DIST
    assert survivor.last_situation.six_evade is True
    assert neutral.last_situation.six_evade is False


def test_opportunist_lowers_powerup_seek_threshold() -> None:
    opp = ARCHETYPE_PROFILES[PilotArchetype.OPPORTUNIST]
    neutral = NEUTRAL_PROFILE
    opp_thresh = config.AI_POWERUP_SEEK_SCORE / opp.powerup_greed
    neutral_thresh = config.AI_POWERUP_SEEK_SCORE / neutral.powerup_greed
    assert opp_thresh < neutral_thresh
    marginal_score = 0.32
    assert marginal_score >= opp_thresh
    assert marginal_score < neutral_thresh


def test_bruiser_commits_reverse_gun_sooner() -> None:
    defender = Ship.create(ShipVariant.BALANCED, (300.0, 300.0), ship_id=1)
    defender.angle = 0.0
    defender.velocity = (95.0, 0.0)
    charger = Ship.create(ShipVariant.HEAVY, (470.0, 300.0), ship_id=2)
    charger.angle = 3.14159265
    charger.velocity = (-120.0, 0.0)
    bruiser = AIController(profile=ARCHETYPE_PROFILES[PilotArchetype.BRUISER])
    neutral = AIController(profile=NEUTRAL_PROFILE)
    bruiser_tick = None
    neutral_tick = None
    for tick in range(60):
        if bruiser_tick is None:
            bruiser.update(defender, [defender, charger], 0.05, [])
            if bruiser.last_context.mode == "reverse_gun":
                bruiser_tick = tick
        if neutral_tick is None:
            neutral.update(defender, [defender, charger], 0.05, [])
            if neutral.last_context.mode == "reverse_gun":
                neutral_tick = tick
        charger.position = (
            charger.position[0] + charger.velocity[0] * 0.05,
            charger.position[1],
        )
        if bruiser_tick is not None and neutral_tick is not None:
            break
    assert bruiser_tick is not None
    assert neutral_tick is not None
    assert bruiser_tick <= neutral_tick