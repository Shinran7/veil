"""Integration tests for game update loop."""

from arena import Arena
from game import GameState, Phase
from ship import ShipVariant


def test_simulation_ticks() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    gs.start_wave()
    for _ in range(30):
        gs.update(0.016, {"thrust": True, "fire": False})
    assert gs.survival_time > 0
    assert gs.player is not None


def test_projectile_kills_enemy() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.HEAVY)
    gs.phase = Phase.PLAYING
    if gs.enemies:
        enemy = gs.enemies[0]
        enemy.health = 1
        from combat import Projectile

        gs.projectiles.append(
            Projectile(
                enemy.position,
                (0.0, 0.0),
                50.0,
                1.0,
                gs.player.ship_id if gs.player else 0,
                enemy.position,
                ShipVariant.HEAVY,
            )
        )
        gs.update(0.016, {})
        assert gs.kills >= 1 or not enemy.alive


def test_ai_arena_winner_heals_between_bouts() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    winner = gs.all_ships[0]
    winner.health = 20.0
    for ship in gs.all_ships[1:]:
        ship.alive = False
    gs.update(0.016, {})
    assert winner.health == winner.max_health


def test_ai_arena_has_asteroid_field() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    assert 2 <= len(gs.arena.obstacles) <= 4


def test_ai_arena_ships_have_distinct_colors() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    colors = {tuple(s.color) for s in gs.all_ships}
    assert len(colors) >= 2


def test_ai_arena_winner_keeps_flying() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    winner = gs.all_ships[0]
    for ship in gs.all_ships[1:]:
        ship.alive = False
    winner.velocity = (80.0, 0.0)
    start = winner.position
    for _ in range(20):
        gs.update(0.05, {})
    assert gs.ai_restart_timer > 0
    assert winner.position != start


def test_ai_arena_single_winner() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    for ship in gs.all_ships[1:]:
        ship.alive = False
    gs.update(0.016, {})
    assert gs.phase == Phase.PLAYING
    assert gs.ai_restart_timer > 0
    assert len(gs.living_ships()) == 1