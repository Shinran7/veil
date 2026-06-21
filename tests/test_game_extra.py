"""Additional game simulation tests."""

from arena import Arena
from game import GameMode, GameState, Phase
from ship import ShipVariant


def test_ai_arena_start() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    assert gs.mode == GameMode.AI_ARENA
    assert len(gs.all_ships) > 0
    assert gs.player is None


def test_toggle_ai_arena_roundtrip() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    gs.toggle_ai_arena()
    assert gs.mode == GameMode.AI_ARENA
    gs.toggle_ai_arena()
    assert gs.mode == GameMode.HUMAN


def test_apply_powerup_on_ship() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_human(ShipVariant.BALANCED)
    gs.start_wave()
    assert gs.player is not None
    gs.player.apply_powerup("shield")
    assert gs.player.shield_timer > 0