"""Projectile vs asteroid collision tests."""

from arena import Arena, Obstacle


def test_projectile_stops_at_asteroid() -> None:
    arena = Arena.from_window(800, 600)
    rock = Obstacle.blocking_at(200.0, 200.0, 30.0)
    arena.obstacles = [rock]
    hit = arena.projectile_hits_obstacle((100.0, 200.0), (250.0, 200.0))
    assert hit is True
    miss = arena.projectile_hits_obstacle((100.0, 100.0), (120.0, 110.0))
    assert miss is False