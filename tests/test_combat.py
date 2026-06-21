"""Tests for combat module."""

from combat import Projectile, fire_weapon, projectile_hits_ship, ships_collide
from ship import Ship, ShipVariant


def test_fire_weapon_creates_projectile() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 100.0), ship_id=1)
    ship.weapon_cooldown = 0
    shots = fire_weapon(ship)
    assert len(shots) == 1
    assert shots[0].owner_id == 1


def test_spread_weapon() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 100.0), ship_id=1)
    ship.weapon_mode = "spread"
    ship.weapon_cooldown = 0
    shots = fire_weapon(ship)
    assert len(shots) == 3


def test_projectile_hits_ship() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (50.0, 50.0), ship_id=2)
    proj = Projectile(
        (50.0, 50.0),
        (0.0, 0.0),
        10.0,
        1.0,
        1,
        (50.0, 50.0),
        ShipVariant.BALANCED,
    )
    assert projectile_hits_ship(proj, ship)


def test_ships_collide() -> None:
    a = Ship.create(ShipVariant.LIGHT, (0.0, 0.0))
    b = Ship.create(ShipVariant.LIGHT, (10.0, 0.0))
    assert ships_collide(a, b)