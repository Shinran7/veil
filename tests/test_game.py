"""Tests for game simulation."""

from arena import Arena
from game import GameState, Phase
from ship import ShipVariant
import config


def test_start_human_sets_wave() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.HEAVY)
    assert gs.player_variant == ShipVariant.HEAVY
    assert gs.wave == 1
    assert gs.phase == Phase.PLAYING
    assert gs.enemy_spawn_timer == 0.0
    assert gs.enemies


def test_wave_clears_to_next() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    gs.start_wave()
    gs.screen_flash = 0.15
    gs.pending_sounds.append("explosion")
    for e in gs.enemies:
        e.alive = False
    gs.update(0.016, {})
    assert gs.enemy_spawn_timer > 0
    assert gs.wave >= 2
    assert gs.screen_flash == 0.0
    assert gs.pending_sounds == []
    assert gs.player is not None
    assert gs.player.health == gs.player.max_health


def test_spawn_timer_player_keeps_moving() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    start = gs.player.position if gs.player else (0.0, 0.0)
    for _ in range(30):
        gs.update(0.05, {"thrust": True})
    assert gs.player is not None
    assert gs.player.position != start


def test_wave_spawn_does_not_teleport_player() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    gs.enemy_spawn_timer = 0.0
    gs.player.position = (120.0, 140.0)
    gs.player.velocity = (50.0, 20.0)
    gs._spawn_wave_enemies()
    assert gs.player.position == (120.0, 140.0)
    assert gs.player.velocity == (50.0, 20.0)


def test_player_death_game_over() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.LIGHT)
    gs.start_wave()
    assert gs.player is not None
    gs.player.spawn_invuln = 0.0
    gs.player.take_damage(9999)
    gs.update(0.016, {})
    assert gs.phase == Phase.GAME_OVER