"""Hit-time range damage and variant projectile behavior."""

import config
from combat import (
    Projectile,
    fire_weapon,
    projectile_hit_damage,
    projectile_speed_for_variant,
    range_damage_multiplier,
)
from ship import Ship, ShipVariant
from utils import vec_len


def test_balanced_fires_faster_bolts() -> None:
    medium = Ship.create(ShipVariant.BALANCED, (0.0, 0.0), ship_id=1)
    heavy = Ship.create(ShipVariant.HEAVY, (0.0, 0.0), ship_id=2)
    medium.weapon_cooldown = 0.0
    heavy.weapon_cooldown = 0.0
    med_shot = fire_weapon(medium)[0]
    heavy_shot = fire_weapon(heavy)[0]
    assert projectile_speed_for_variant(ShipVariant.BALANCED) > config.PROJECTILE_SPEED
    assert vec_len(med_shot.velocity) > vec_len(heavy_shot.velocity)


def test_light_hits_harder_up_close() -> None:
    close = range_damage_multiplier(ShipVariant.LIGHT, 0.0)
    far = range_damage_multiplier(ShipVariant.LIGHT, config.PROJECTILE_RANGE_DAMAGE_REF)
    assert close > far
    assert close == config.RANGE_DAMAGE_LIGHT[0]
    assert far == config.RANGE_DAMAGE_LIGHT[1]


def test_heavy_hits_harder_at_range() -> None:
    close = range_damage_multiplier(ShipVariant.HEAVY, 0.0)
    far = range_damage_multiplier(ShipVariant.HEAVY, config.PROJECTILE_RANGE_DAMAGE_REF)
    assert far > close
    assert close == config.RANGE_DAMAGE_HEAVY[0]
    assert far == config.RANGE_DAMAGE_HEAVY[1]
    assert far > close


def test_balanced_peaks_at_mid_range() -> None:
    edge = range_damage_multiplier(ShipVariant.BALANCED, 0.0)
    mid = range_damage_multiplier(
        ShipVariant.BALANCED, config.PROJECTILE_RANGE_DAMAGE_REF * 0.5
    )
    assert mid > edge
    assert mid == config.RANGE_DAMAGE_BALANCED_PEAK


def test_projectile_hit_damage_uses_travel_distance() -> None:
    ship = Ship.create(ShipVariant.LIGHT, (0.0, 0.0), ship_id=1)
    ship.weapon_cooldown = 0.0
    proj = fire_weapon(ship)[0]
    proj.position = (proj.origin[0] + 80.0, proj.origin[1])
    close_dmg = projectile_hit_damage(proj)
    proj.position = (
        proj.origin[0] + config.PROJECTILE_RANGE_DAMAGE_REF * 0.9,
        proj.origin[1],
    )
    far_dmg = projectile_hit_damage(proj)
    assert close_dmg > far_dmg