"""Boss bout easter egg after a final-two double KO."""

from arena import Arena
from game import GameMode, GameState
from ship import Ship, ShipVariant


def _arena() -> Arena:
    return Arena.from_window(900, 600)


def test_double_ko_schedules_boss_bout() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    gs.arena = _arena()
    a = Ship.create(ShipVariant.HEAVY, (200.0, 300.0), ship_id=1)
    b = Ship.create(ShipVariant.LIGHT, (500.0, 300.0), ship_id=2)
    a.alive = False
    b.alive = False
    gs.all_ships = [a, b]
    gs.ai_prev_living_count = 2
    gs._update_ai_arena(0.05)
    assert gs.ai_pending_boss_bout is True
    assert gs.ai_restart_timer == 5.0


def test_boss_bout_spawns_two_evolved_heavies() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    gs.arena = _arena()
    gs.ai_pending_boss_bout = True
    gs.ai_restart_timer = 0.01
    gs._update_ai_arena(0.05)
    assert len(gs.all_ships) == 2
    assert all(s.is_boss_evolved for s in gs.all_ships)
    assert all(s.variant == ShipVariant.HEAVY for s in gs.all_ships)
    assert gs.ai_boss_bout_active is True