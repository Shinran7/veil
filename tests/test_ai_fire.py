"""AI firing behavior tests."""

from arena import Arena
from game import GameMode, GameState
from ship import ShipVariant


def test_ai_fires_in_arena_mode() -> None:
    gs = GameState()
    gs.arena = Arena.from_window(800, 600)
    gs.start_ai_arena()
    fired = False
    for _ in range(80):
        gs.update(0.05, {})
        if gs.projectiles or "fire_enemy" in gs.pending_sounds:
            fired = True
            break
    assert fired