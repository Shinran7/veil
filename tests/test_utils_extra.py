"""Extra utils tests."""

from utils import world_polygon, wrap_position, wrapped_delta, wrapped_distance


def test_world_polygon_offset() -> None:
    hull = [(0.0, -10.0), (10.0, 0.0), (0.0, 10.0)]
    poly = world_polygon(hull, (100.0, 100.0), 0.0)
    assert poly[0][1] == 90.0


def test_wrap_position_edges() -> None:
    rect = (0.0, 0.0, 100.0, 80.0)
    assert wrap_position((-1.0, 40.0), rect) == (99.0, 40.0)
    assert wrap_position((101.0, 40.0), rect) == (1.0, 40.0)
    assert wrap_position((50.0, -2.0), rect) == (50.0, 78.0)
    assert wrap_position((50.0, 82.0), rect) == (50.0, 2.0)


def test_wrapped_distance_across_edges() -> None:
    rect = (0.0, 0.0, 800.0, 600.0)
    assert wrapped_distance((400.0, 20.0), (400.0, 580.0), rect) == 40.0
    delta = wrapped_delta((400.0, 20.0), (400.0, 580.0), rect)
    assert delta == (0.0, -40.0)