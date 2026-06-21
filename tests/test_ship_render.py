"""Ship hull geometry tests."""

from ship import Ship, ShipVariant
from utils import vec_len, vec_sub


def test_hull_points_centered_on_ship() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), is_player=True)
    pts = ship.hull_points()
    assert len(pts) >= 4
    for p in pts:
        assert vec_len(vec_sub(p, ship.position)) < 30


def test_hull_rotates_with_angle() -> None:
    ship = Ship.create(ShipVariant.LIGHT, (200.0, 200.0))
    ship.angle = 1.57
    pts = ship.hull_points()
    nose = max(pts, key=lambda p: p[0])
    assert nose[0] > ship.position[0]


def test_heavy_has_aux_hulls_and_three_nozzles() -> None:
    ship = Ship.create(ShipVariant.HEAVY, (300.0, 300.0))
    assert len(ship.aux_hull_points()) == 3
    assert len(ship.engine_nozzles()) == 3


def test_boss_hull_lines_scale_without_crash() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (400.0, 300.0), ship_id=1)
    ship.champion_wins = 5
    ship.apply_champion_bonuses()
    assert ship.is_boss_evolved
    nose_a, nose_b = ship.nose_line()
    assert vec_len(vec_sub(nose_a, ship.position)) > 0
    assert len(ship.panel_lines()) == 2