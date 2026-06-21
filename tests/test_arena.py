"""Tests for arena module."""

from arena import Arena


def test_enemy_count_scales_with_wave() -> None:
    arena = Arena.from_window(800, 600)
    w1 = arena.enemy_count_for_wave(1)
    w5 = arena.enemy_count_for_wave(5)
    assert w5 >= w1
    assert 2 <= w1 <= 10


def test_stars_have_twinkle_metadata() -> None:
    arena = Arena.from_window(800, 600)
    assert len(arena.stars) == 120
    assert all(len(star) == 6 for star in arena.stars)
    assert any(star[5] > 0 for star in arena.stars)


def test_asteroid_field_count() -> None:
    arena = Arena.from_window(800, 600)
    arena.init_asteroid_field(3)
    assert len(arena.obstacles) == 3


def test_asteroid_drifts_off_screen() -> None:
    arena = Arena.from_window(800, 600)
    rock = arena._spawn_asteroid_from_edge()
    rock.velocity = (-200.0, 0.0)
    rock.center = (20.0, 300.0)
    for _ in range(60):
        arena.update_asteroids(0.05)
    assert rock not in arena.obstacles


def test_asteroid_minimum_replenished() -> None:
    arena = Arena.from_window(800, 600)
    arena.init_asteroid_field(2)
    arena.obstacles.clear()
    arena.update_asteroids(0.016)
    assert len(arena.obstacles) >= 2