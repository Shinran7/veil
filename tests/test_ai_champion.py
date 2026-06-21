"""Champion bout respawn tests."""

import config
from combat import PowerUpKind
from game import GameMode, GameState, Phase
from ship import Ship, ShipVariant


def test_fresh_bout_spawns_five_newcomers() -> None:
    gs = GameState()
    assert gs._contender_slots(1, 0) == 5


def test_reigning_champ_faces_five_newcomers() -> None:
    gs = GameState()
    assert gs._contender_slots(1, 1) == 5
    assert gs._contender_slots(1, 5) == 5


def test_reigning_champ_respawns_five_opponents() -> None:
    gs = GameState()
    gs.arena = __import__("arena").Arena.from_window(800, 600)
    champ = Ship.create(ShipVariant.HEAVY, (400.0, 300.0), ship_id=1)
    champ.champion_wins = 2
    champ.apply_champion_bonuses()
    gs.all_ships = [champ]
    gs.enemies = gs.all_ships
    gs.ai_controllers = {}
    gs._respawn_ai_opponents()
    assert len(gs.all_ships) == 6


def test_streak_champion_gets_bout_shield_drop() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    gs.arena = __import__("arena").Arena.from_window(800, 600)
    champ = Ship.create(ShipVariant.HEAVY, (400.0, 300.0), ship_id=1)
    champ.champion_wins = 2
    champ.apply_champion_bonuses()
    gs.phase = Phase.PLAYING
    gs.all_ships = [champ]
    gs.enemies = gs.all_ships
    gs.ai_restart_timer = 0.01
    gs.update(0.02, {})
    assert len(gs.all_ships) == 6
    assert any(pu.kind == PowerUpKind.SHIELD for pu in gs.powerups)


def test_champion_gets_bout_start_invuln() -> None:
    gs = GameState()
    gs.mode = GameMode.AI_ARENA
    gs.arena = __import__("arena").Arena.from_window(800, 600)
    champ = Ship.create(ShipVariant.HEAVY, (400.0, 300.0), ship_id=1)
    champ.champion_wins = 1
    gs.phase = Phase.PLAYING
    gs.all_ships = [champ]
    gs.enemies = gs.all_ships
    gs.ai_restart_timer = 0.01
    gs.update(0.02, {})
    assert champ.spawn_invuln == GameState._champion_bout_invuln(1)