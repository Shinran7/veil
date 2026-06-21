"""Power-up vs asteroid collision tests."""

from arena import Arena, Obstacle
from combat import PowerUp, PowerUpKind
from utils import vec_len, vec_sub


def test_powerup_pushed_by_asteroid() -> None:
    arena = Arena.from_window(800, 600)
    rock = Obstacle.create(200.0, 300.0, 40.0, velocity=(30.0, 0.0))
    arena.obstacles = [rock]
    pu = PowerUp(PowerUpKind.SHIELD, (210.0, 300.0))
    start = pu.position
    arena.resolve_powerup_obstacle_collisions([pu])
    assert pu.position != start
    assert vec_len(pu.velocity) > 0.0
    assert vec_len(vec_sub(pu.position, rock.center)) > pu.radius + rock.radius - 1.0


def test_asteroids_separate_on_overlap() -> None:
    arena = Arena.from_window(800, 600)
    a = Obstacle.create(200.0, 300.0, 40.0, velocity=(25.0, 0.0))
    b = Obstacle.create(235.0, 300.0, 38.0, velocity=(-20.0, 0.0))
    arena.obstacles = [a, b]
    arena.resolve_obstacle_collisions()
    assert (
        vec_len(vec_sub(b.center, a.center))
        >= a.collision_radius + b.collision_radius - 0.5
    )


def test_asteroids_bounce_on_head_on_overlap() -> None:
    arena = Arena.from_window(800, 600)
    a = Obstacle.create(200.0, 300.0, 40.0, velocity=(80.0, 0.0))
    b = Obstacle.create(235.0, 300.0, 40.0, velocity=(-80.0, 0.0))
    arena.obstacles = [a, b]
    arena.resolve_obstacle_collisions()
    assert a.velocity[0] < 80.0
    assert b.velocity[0] > -80.0


def test_collision_radius_matches_hull() -> None:
    rock = Obstacle.create(100.0, 100.0, 40.0, seed=42)
    assert rock.collision_radius >= rock.radius
    assert rock.collision_radius == max(vec_len(v) for v in rock.local_vertices)


def test_powerup_drifts_after_nudge() -> None:
    pu = PowerUp(PowerUpKind.FIRE_RATE, (100.0, 100.0))
    pu.velocity = (50.0, 0.0)
    pu.update(0.1)
    assert pu.position[0] > 100.0