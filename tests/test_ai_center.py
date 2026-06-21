"""AI center-field bias and inner spawn tests."""

import config
from ai import AIController
from arena import Arena
from ship import Ship, ShipVariant


ARENA = (0.0, 0.0, 800.0, 600.0)


def test_edge_ship_prefers_direct_chase_over_wrap_shortcut() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (400.0, 20.0), ship_id=1)
    target = Ship.create(ShipVariant.LIGHT, (400.0, 580.0), ship_id=2)
    ctrl = AIController.for_ship(ship)
    delta = ctrl._target_delta(ship, target, ARENA)
    assert delta[1] > 200.0


def test_aim_biases_toward_center_near_wall() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (30.0, 300.0), ship_id=1)
    ctrl = AIController.for_ship(ship)
    biased = ctrl._bias_aim_toward_center(ship, (900.0, 300.0), ARENA)
    assert biased[0] < 900.0
    assert abs(biased[1] - 300.0) < 5.0


def test_inner_spawn_stays_off_screen_edge() -> None:
    arena = Arena.from_window(1280, 768)
    x, y, w, h = arena.rect
    inset = config.ARENA_SPAWN_INSET_FRAC
    for _ in range(40):
        px, py = arena.spawn_point_inner()
        assert px >= x + w * inset
        assert px <= x + w * (1.0 - inset)
        assert py >= y + h * inset
        assert py <= y + h * (1.0 - inset)