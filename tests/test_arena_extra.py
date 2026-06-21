"""Additional arena tests."""

from arena import Arena
from ship import Ship, ShipVariant


def test_spawn_enemies_variants() -> None:
    arena = Arena.from_window(800, 600)
    ships, _ = arena.spawn_enemies(3, 10)
    assert len(ships) >= 2
    assert all(s.ai_controlled for s in ships)


def test_obstacle_collision() -> None:
    arena = Arena.from_window(800, 600)
    arena.init_asteroid_field(2)
    ship = Ship.create(ShipVariant.BALANCED, (200.0, 200.0))
    if arena.obstacles:
        obs = arena.obstacles[0]
        ship.position = obs.center
        assert arena.ship_hits_obstacle(ship)
        arena.resolve_obstacle_collision(ship)