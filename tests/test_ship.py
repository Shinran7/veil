"""Tests for ship module."""

from ship import ENEMY_COLORS, Ship, ShipVariant, pick_enemy_color


def test_ship_create_player() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (100.0, 100.0), is_player=True)
    assert ship.alive
    assert ship.is_player
    assert ship.health == ship.max_health


def test_ram_damage_heavy_vs_light() -> None:
    heavy = Ship.create(ShipVariant.HEAVY, (0.0, 0.0))
    light = Ship.create(ShipVariant.LIGHT, (10.0, 0.0))
    heavy_self, heavy_tgt = heavy.ram_damage(200.0)
    light_self, light_tgt = light.ram_damage(200.0)
    assert heavy_self < light_self
    assert heavy_tgt > light_tgt


def test_take_damage_kills() -> None:
    ship = Ship.create(ShipVariant.LIGHT, (0.0, 0.0))
    destroyed = ship.take_damage(999.0)
    assert destroyed
    assert not ship.alive


def test_pick_enemy_color_from_palette() -> None:
    assert pick_enemy_color() in ENEMY_COLORS


def test_enemy_color_override() -> None:
    ship = Ship.create(
        ShipVariant.BALANCED,
        (0.0, 0.0),
        enemy_color=(65, 215, 130),
    )
    assert ship.color == (65, 215, 130)


def test_shield_reduces_damage() -> None:
    ship = Ship.create(ShipVariant.BALANCED, (0.0, 0.0))
    ship.shield_timer = 5.0
    ship.take_damage(100.0)
    assert ship.health > 0