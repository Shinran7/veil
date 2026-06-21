"""Combat integration tests."""

from combat import (
    PowerUp,
    PowerUpKind,
    collision_impact_speed,
    resolve_ship_collision,
    ships_collide,
)
from ship import Ship, ShipVariant
from utils import vec_len, vec_sub


def test_ram_collision_damage() -> None:
    a = Ship.create(ShipVariant.HEAVY, (0.0, 0.0), ship_id=1)
    b = Ship.create(ShipVariant.LIGHT, (20.0, 0.0), ship_id=2)
    a.velocity = (100.0, 0.0)
    b.velocity = (-80.0, 0.0)
    assert ships_collide(a, b)
    impact = collision_impact_speed(a, b)
    a_self, a_tgt = a.ram_damage(impact)
    b_self, b_tgt = b.ram_damage(impact)
    assert b_self > a_self


def test_ships_separate_and_bounce_on_ram() -> None:
    a = Ship.create(ShipVariant.HEAVY, (0.0, 0.0), ship_id=1)
    b = Ship.create(ShipVariant.HEAVY, (30.0, 0.0), ship_id=2)
    a.velocity = (120.0, 0.0)
    b.velocity = (-100.0, 0.0)
    impact = resolve_ship_collision(a, b)
    assert impact >= 200.0
    assert vec_len(vec_sub(b.position, a.position)) >= a.radius + b.radius - 0.5
    assert b.velocity[0] > 0.0
    assert a.velocity[0] < 0.0


def test_powerup_lifetime() -> None:
    pu = PowerUp(PowerUpKind.SPREAD, (0.0, 0.0), lifetime=0.1)
    pu.update(0.2)
    assert not pu.alive