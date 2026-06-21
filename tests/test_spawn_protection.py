"""Spawn protection and placement tests."""

from arena import Arena
from game import GameState, Phase
from ship import Ship, ShipVariant
from utils import vec_len, vec_sub
import config


def test_enemies_spawn_away_from_player() -> None:
    arena = Arena.from_window(800, 600)
    player_pos = arena.player_spawn_point()
    enemies, _ = arena.spawn_enemies(1, 1, avoid=player_pos)
    assert enemies
    dist = vec_len(vec_sub(enemies[0].position, player_pos))
    assert dist >= config.SPAWN_MIN_DISTANCE * 0.5


def test_spawn_invuln_blocks_damage() -> None:
    ship = Ship.create(ShipVariant.LIGHT, (0.0, 0.0))
    ship.spawn_invuln = 1.0
    assert not ship.take_damage(999.0)
    assert ship.alive


def test_spawn_timer_before_first_wave() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    assert gs.phase == Phase.PLAYING
    assert gs.enemies
    assert gs.player is not None
    assert gs.enemy_spawn_timer == 0.0