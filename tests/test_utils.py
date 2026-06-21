"""Tests for utils module."""

from utils import clamp, vec_add, vec_len, vec_norm, circle_rect_collision


def test_vec_add() -> None:
    assert vec_add((1.0, 2.0), (3.0, 4.0)) == (4.0, 6.0)


def test_vec_len() -> None:
    assert vec_len((3.0, 4.0)) == 5.0


def test_vec_norm() -> None:
    n = vec_norm((10.0, 0.0))
    assert abs(n[0] - 1.0) < 1e-6


def test_clamp() -> None:
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(99, 0, 10) == 10


def test_circle_rect_collision() -> None:
    assert circle_rect_collision((50.0, 50.0), 10.0, (40.0, 40.0, 20.0, 20.0))
    assert not circle_rect_collision((0.0, 0.0), 5.0, (100.0, 100.0, 20.0, 20.0))