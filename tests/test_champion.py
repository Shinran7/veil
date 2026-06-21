"""AI champion streak and power-up pacing tests."""

import pytest

import config
from game import GameMode, GameState
from ship import Ship, ShipVariant


def test_fifth_win_evolves_boss() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 100.0), ship_id=1)
    ship.champion_wins = 4
    ship.apply_champion_bonuses()
    assert not ship.is_boss_evolved
    ship.champion_wins = 5
    ship.apply_champion_bonuses()
    assert ship.is_boss_evolved
    assert ship.radius > ship.base_radius
    assert ship.max_health > ship.base_max_health * 1.62


def test_champion_bout_invuln_scales_early_wins() -> None:
    assert GameState._champion_bout_invuln(1) == pytest.approx(2.0)
    assert GameState._champion_bout_invuln(3) == pytest.approx(2.8)
    assert GameState._champion_bout_invuln(8) == pytest.approx(2.8)


def test_champion_gains_bout_win() -> None:
    winner = Ship.create(ShipVariant.BALANCED, (100.0, 100.0), ship_id=1)
    winner.champion_wins += 1
    winner.apply_champion_bonuses()
    assert winner.champion_wins == 1
    assert winner.max_health == winner.base_max_health * 1.18
    assert winner.thrust_power == winner.base_thrust_power * 1.13


def test_five_stacks_match_flat_totals() -> None:
    assert Ship._stacked_bonus(5, config.CHAMPION_HEALTH_BY_STACK) == pytest.approx(0.55)
    assert Ship._stacked_bonus(5, config.CHAMPION_THRUST_BY_STACK) == pytest.approx(0.40)
    assert Ship._stacked_bonus(5, config.CHAMPION_FIRE_BY_STACK) == pytest.approx(0.45)

    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    ship.champion_wins = 4
    ship.apply_champion_bonuses()
    assert not ship.is_boss_evolved
    assert ship.max_health == pytest.approx(ship.base_max_health * 1.515)
    assert ship.thrust_power == pytest.approx(ship.base_thrust_power * 1.37)
    base_cd = Ship.create(ShipVariant.BALANCED, (0.0, 0.0)).effective_fire_cooldown()
    assert ship.effective_fire_cooldown() == pytest.approx(base_cd * 0.585)


def test_boss_pulse_damages_nearby() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    boss = Ship.create(ShipVariant.HEAVY, (200.0, 200.0), ship_id=1)
    boss.champion_wins = 5
    boss.apply_champion_bonuses()
    rival = Ship.create(ShipVariant.LIGHT, (240.0, 200.0), ship_id=2)
    boss.boss_pulse_timer = 0.0
    gs._tick_boss_pulses([boss, rival], 0.016)
    assert boss.boss_pulse_flash > 0
    assert rival.health < rival.max_health


def test_champion_resets_on_death() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    gs.arena = __import__("arena").Arena.from_window(800, 600)
    ship = Ship.create(ShipVariant.LIGHT, (200.0, 200.0), ship_id=2)
    ship.champion_wins = 5
    ship.apply_champion_bonuses()
    assert ship.is_boss_evolved
    gs._on_ship_destroyed(ship)
    assert ship.champion_wins == 0
    assert not ship.is_boss_evolved
    assert ship.max_health == ship.base_max_health


def test_powerup_spawn_timer_fills_field() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    gs.arena = __import__("arena").Arena.from_window(800, 600)
    gs.start_ai_arena()
    start_count = len(gs.powerups)
    for _ in range(200):
        gs._tick_powerup_spawns(0.05, gs.arena.rect)
    assert start_count >= config.POWERUP_BOUT_START_COUNT
    assert len(gs.powerups) >= 1