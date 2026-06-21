"""Ship entity and variants."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import config
from utils import (
    Vec2,
    clamp,
    rotate_point,
    vec_add,
    vec_from_angle,
    vec_len,
    vec_scale,
    world_polygon,
    wrap_position,
)

if TYPE_CHECKING:
    from combat import WeaponMode


class ShipVariant(str, Enum):
    LIGHT = "light"
    BALANCED = "balanced"
    HEAVY = "heavy"


VARIANT_STATS: dict[ShipVariant, dict[str, float]] = {
    ShipVariant.LIGHT: {
        "max_health": 135,
        "thrust": 300,
        "turn_rate": 4.5,
        "radius": 14,
        "ram_self": 1.35,
        "ram_target": 1.0,
        "fire_cooldown_mult": 0.76,
        "damage_dealt_mult": 1.12,
        "damage_taken_mult": 0.88,
        "color": (180, 220, 255),
    },
    ShipVariant.BALANCED: {
        "max_health": 165,
        "thrust": 240,
        "turn_rate": 3.6,
        "radius": 16,
        "ram_self": 1.0,
        "ram_target": 1.0,
        "fire_cooldown_mult": 1.0,
        "damage_dealt_mult": 1.0,
        "damage_taken_mult": 1.0,
        "color": (120, 200, 255),
    },
    ShipVariant.HEAVY: {
        "max_health": 228,
        "thrust": 180,
        "turn_rate": 2.6,
        "radius": 20,
        "ram_self": 0.28,
        "ram_target": 1.6,
        "fire_cooldown_mult": 1.04,
        "damage_dealt_mult": 0.98,
        "damage_taken_mult": 0.94,
        "color": (80, 160, 255),
    },
}

ENEMY_COLORS = [
    (255, 90, 60),
    (255, 150, 45),
    (255, 75, 110),
    (170, 95, 255),
    (65, 215, 130),
    (255, 225, 65),
    (55, 195, 255),
    (255, 105, 255),
]


def pick_enemy_color() -> tuple[int, int, int]:
    return random.choice(ENEMY_COLORS)

HULLS: dict[ShipVariant, list[Vec2]] = {
    ShipVariant.LIGHT: [
        (20, 0), (6, -3), (-4, -5), (-12, -3), (-14, 0), (-12, 3), (-4, 5), (6, 3),
    ],
    ShipVariant.BALANCED: [
        (24, 0), (12, -4), (4, -8), (-4, -11), (-14, -6), (-17, 0), (-14, 6),
        (-4, 11), (4, 8), (12, 4),
    ],
    ShipVariant.HEAVY: [
        (28, 0), (14, -3), (6, -5), (-2, -12), (-10, -17), (-16, -12), (-20, -5),
        (-23, 0), (-20, 5), (-16, 12), (-10, 17), (-2, 12), (6, 5), (14, 3),
    ],
}

# Secondary hull chunks (boosters, engine block) in local space
AUX_HULLS: dict[ShipVariant, list[list[Vec2]]] = {
    ShipVariant.LIGHT: [],
    ShipVariant.BALANCED: [],
    ShipVariant.HEAVY: [
        [(-12, -8), (-19, -6), (-19, -2), (-12, -4)],
        [(-12, 8), (-19, 6), (-19, 2), (-12, 4)],
        [(-20, -6), (-23, -4), (-23, 4), (-20, 6)],
    ],
}

# Inner fuselage highlight strip
HULL_HIGHLIGHTS: dict[ShipVariant, list[Vec2]] = {
    ShipVariant.LIGHT: [(16, 0), (4, -2), (-6, -2), (-10, 0), (-6, 2), (4, 2)],
    ShipVariant.BALANCED: [(18, 0), (6, -3), (-4, -4), (-12, 0), (-4, 4), (6, 3)],
    ShipVariant.HEAVY: [(20, 0), (8, -2), (-2, -4), (-14, -2), (-16, 0), (-14, 2), (-2, 4), (8, 2)],
}

# Accent panel lines in local hull space (nose = +x)
HULL_PANELS: dict[ShipVariant, list[tuple[Vec2, Vec2]]] = {
    ShipVariant.LIGHT: [((-6, -4), (-6, 4))],
    ShipVariant.BALANCED: [((-8, -5), (-8, 5)), ((2, -4), (2, 4))],
    ShipVariant.HEAVY: [
        ((-4, -10), (-10, -14)), ((-4, 10), (-10, 14)),
        ((-14, -3), (-18, -5)), ((-14, 3), (-18, 5)),
    ],
}

# Round porthole center in local hull space
COCKPIT_WINDOWS: dict[ShipVariant, Vec2] = {
    ShipVariant.LIGHT: (4, 0),
    ShipVariant.BALANCED: (7, 0),
    ShipVariant.HEAVY: (10, 0),
}

NOSE_LINES: dict[ShipVariant, tuple[Vec2, Vec2]] = {
    ShipVariant.LIGHT: ((18, 0), (2, 0)),
    ShipVariant.BALANCED: ((20, 0), (0, 0)),
    ShipVariant.HEAVY: ((24, 0), (2, 0)),
}


@dataclass
class Ship:
    variant: ShipVariant
    position: Vec2
    velocity: Vec2 = (0.0, 0.0)
    angle: float = 0.0
    angular_velocity: float = 0.0
    health: float = 0.0
    max_health: float = 0.0
    thrust_power: float = 0.0
    turn_rate: float = 0.0
    radius: float = 14.0
    ram_self_mult: float = 1.0
    ram_target_mult: float = 1.0
    color: tuple[int, int, int] = (120, 200, 255)
    is_player: bool = False
    alive: bool = True
    weapon_cooldown: float = 0.0
    shield_timer: float = 0.0
    fire_rate_timer: float = 0.0
    spread_timer: float = 0.0
    weapon_mode: str = "primary"
    ai_controlled: bool = False
    ship_id: int = 0
    spawn_invuln: float = 0.0
    base_max_health: float = 0.0
    base_thrust_power: float = 0.0
    base_radius: float = 14.0
    champion_wins: int = 0
    is_boss_evolved: bool = False
    boss_pulse_timer: float = 0.0
    boss_pulse_flash: float = 0.0

    @classmethod
    def create(
        cls,
        variant: ShipVariant,
        position: Vec2,
        *,
        is_player: bool = False,
        angle: float = 0.0,
        ship_id: int = 0,
        enemy_color: tuple[int, int, int] | None = None,
    ) -> Ship:
        stats = VARIANT_STATS[variant]
        color = stats["color"] if is_player else (enemy_color or ENEMY_COLORS[0])
        ship = cls(
            variant=variant,
            position=position,
            angle=angle,
            health=stats["max_health"],
            max_health=stats["max_health"],
            thrust_power=stats["thrust"],
            turn_rate=stats["turn_rate"],
            radius=stats["radius"],
            ram_self_mult=stats["ram_self"],
            ram_target_mult=stats["ram_target"],
            color=color,
            is_player=is_player,
            ship_id=ship_id,
            base_max_health=stats["max_health"],
            base_thrust_power=stats["thrust"],
            base_radius=stats["radius"],
        )
        ship.apply_champion_bonuses()
        return ship

    def hull_scale(self) -> float:
        return config.BOSS_HULL_SCALE if self.is_boss_evolved else 1.0

    def _scaled_local(self, points: list[Vec2]) -> list[Vec2]:
        scale = self.hull_scale()
        if scale == 1.0:
            return points
        return [(x * scale, y * scale) for x, y in points]

    def hull_points(self) -> list[Vec2]:
        return world_polygon(
            self._scaled_local(HULLS[self.variant]), self.position, self.angle
        )

    def aux_hull_points(self) -> list[list[Vec2]]:
        return [
            world_polygon(self._scaled_local(chunk), self.position, self.angle)
            for chunk in AUX_HULLS[self.variant]
        ]

    def highlight_points(self) -> list[Vec2]:
        hull = HULL_HIGHLIGHTS.get(self.variant, [])
        if not hull:
            return []
        return world_polygon(self._scaled_local(hull), self.position, self.angle)

    def nose_line(self) -> tuple[Vec2, Vec2]:
        a, b = NOSE_LINES[self.variant]
        sa, sb = self._scaled_local([a, b])
        return (
            vec_add(rotate_point(sa, self.angle), self.position),
            vec_add(rotate_point(sb, self.angle), self.position),
        )

    def panel_lines(self) -> list[tuple[Vec2, Vec2]]:
        lines: list[tuple[Vec2, Vec2]] = []
        for a, b in HULL_PANELS[self.variant]:
            sa, sb = self._scaled_local([a, b])
            la = vec_add(rotate_point(sa, self.angle), self.position)
            lb = vec_add(rotate_point(sb, self.angle), self.position)
            lines.append((la, lb))
        return lines

    def engine_nozzles(self) -> list[Vec2]:
        """Exhaust port positions in world space."""
        back_dist = 0.5 if self.variant == ShipVariant.HEAVY else 0.55
        back = vec_add(self.position, vec_from_angle(self.angle + math.pi, self.radius * back_dist))
        if self.variant == ShipVariant.HEAVY:
            spread = 8
            center = vec_add(back, vec_from_angle(self.angle + math.pi, 4))
            left = vec_add(back, vec_from_angle(self.angle + math.pi + 1.57, spread))
            right = vec_add(back, vec_from_angle(self.angle + math.pi - 1.57, spread))
            return [left, center, right]
        spread = 5 if self.variant == ShipVariant.LIGHT else 7
        left = vec_add(back, vec_from_angle(self.angle + math.pi + 1.57, spread))
        right = vec_add(back, vec_from_angle(self.angle + math.pi - 1.57, spread))
        return [left, right]

    def engine_points(self) -> tuple[Vec2, Vec2]:
        nozzles = self.engine_nozzles()
        return nozzles[0], nozzles[-1]

    def window_center(self) -> Vec2:
        local = COCKPIT_WINDOWS[self.variant]
        return vec_add(rotate_point(local, self.angle), self.position)

    def window_radius(self) -> float:
        base = 4.5 if self.variant == ShipVariant.HEAVY else 3.5
        if self.variant == ShipVariant.LIGHT:
            base = 2.8
        return base * self.hull_scale()

    def fin_lines(self) -> list[tuple[Vec2, Vec2]]:
        """Side fin accent lines in world space."""
        if self.variant == ShipVariant.LIGHT:
            local = [((-4, -5), (-10, -3)), ((-4, 5), (-10, 3))]
        elif self.variant == ShipVariant.BALANCED:
            local = [((-6, -9), (-14, -5)), ((-6, 9), (-14, 5))]
        else:
            local = [
                ((2, -12), (-10, -16)), ((2, 12), (-10, 16)),
                ((-12, -7), (-19, -5)), ((-12, 7), (-19, 5)),
            ]
        lines: list[tuple[Vec2, Vec2]] = []
        for a, b in local:
            la = vec_add(rotate_point(a, self.angle), self.position)
            lb = vec_add(rotate_point(b, self.angle), self.position)
            lines.append((la, lb))
        return lines

    def cockpit_point(self) -> Vec2:
        return vec_add(self.position, vec_from_angle(self.angle, self.radius * 0.4))

    def apply_thrust(self, direction: float, dt: float) -> None:
        thrust_vec = vec_from_angle(self.angle + direction, self.thrust_power)
        self.velocity = vec_add(self.velocity, vec_scale(thrust_vec, dt))

    def apply_rotation(self, direction: float, dt: float) -> None:
        self.angular_velocity += direction * self.turn_rate * dt
        self.angle += self.angular_velocity * dt
        self.angular_velocity *= config.ANGULAR_DRAG

    def update_physics(self, dt: float, arena_rect: tuple[float, float, float, float]) -> None:
        if not self.alive:
            return
        self.position = vec_add(self.position, vec_scale(self.velocity, dt))
        self.velocity = vec_scale(self.velocity, config.DRAG)
        speed = vec_len(self.velocity)
        if speed > config.MAX_SPEED:
            self.velocity = vec_scale(self.velocity, config.MAX_SPEED / speed)

        if self.weapon_cooldown > 0:
            self.weapon_cooldown -= dt
        if self.shield_timer > 0:
            self.shield_timer -= dt
        if self.fire_rate_timer > 0:
            self.fire_rate_timer -= dt
        if self.spread_timer > 0:
            self.spread_timer -= dt
            if self.spread_timer <= 0:
                self.weapon_mode = "primary"
        if self.spawn_invuln > 0:
            self.spawn_invuln = max(0.0, self.spawn_invuln - dt)

        self.position = wrap_position(self.position, arena_rect)

    def take_damage(self, amount: float) -> bool:
        if not self.alive or self.spawn_invuln > 0:
            return False
        if self.shield_timer > 0:
            amount *= 0.25
        amount *= VARIANT_STATS[self.variant].get("damage_taken_mult", 1.0)
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.alive = False
            return True
        return False

    def ram_damage(self, impact_speed: float) -> tuple[float, float]:
        """Return (self_damage, target_damage) for collision."""
        base = config.RAM_BASE_DAMAGE * (impact_speed / 200.0)
        return base * self.ram_self_mult, base * self.ram_target_mult

    def champion_stacks(self) -> int:
        return min(self.champion_wins, config.CHAMPION_MAX_STACKS)

    @staticmethod
    def _stacked_bonus(stacks: int, per_stack: list[float]) -> float:
        return sum(per_stack[:stacks])

    def apply_champion_bonuses(self) -> None:
        should_boss = self.champion_wins >= config.CHAMPION_BOSS_WINS
        if should_boss and not self.is_boss_evolved:
            self.is_boss_evolved = True
            self.boss_pulse_timer = config.BOSS_PULSE_COOLDOWN * 0.45
        elif not should_boss:
            self.is_boss_evolved = False
            self.boss_pulse_timer = 0.0
            self.boss_pulse_flash = 0.0
        stacks = self.champion_stacks()
        health_mult = 1.0 + self._stacked_bonus(
            stacks, config.CHAMPION_HEALTH_BY_STACK
        )
        thrust_mult = 1.0 + self._stacked_bonus(
            stacks, config.CHAMPION_THRUST_BY_STACK
        )
        if self.is_boss_evolved:
            health_mult *= config.BOSS_HEALTH_MULT
            thrust_mult *= config.BOSS_THRUST_MULT
        self.max_health = self.base_max_health * health_mult
        self.thrust_power = self.base_thrust_power * thrust_mult
        self.radius = self.base_radius * (
            config.BOSS_HULL_SCALE if self.is_boss_evolved else 1.0
        )
        if self.alive:
            self.health = min(self.max_health, self.health)

    def effective_fire_cooldown(self) -> float:
        mult = VARIANT_STATS[self.variant].get("fire_cooldown_mult", 1.0)
        champ = 1.0 - self._stacked_bonus(
            self.champion_stacks(), config.CHAMPION_FIRE_BY_STACK
        )
        if self.is_boss_evolved:
            champ *= config.BOSS_FIRE_MULT
        if self.fire_rate_timer > 0:
            return config.FIRE_COOLDOWN * config.FIRE_RATE_COOLDOWN_MULT * mult * champ
        if self.weapon_mode == "spread":
            return config.SPREAD_COOLDOWN * mult * champ
        return config.FIRE_COOLDOWN * mult * champ

    def can_fire(self) -> bool:
        return self.alive and self.weapon_cooldown <= 0

    def mark_fired(self) -> None:
        self.weapon_cooldown = self.effective_fire_cooldown()

    def apply_powerup(self, kind: str) -> None:
        if kind == "shield":
            self.shield_timer = config.SHIELD_DURATION
        elif kind == "fire_rate":
            self.fire_rate_timer = config.FIRE_RATE_DURATION
        elif kind == "spread":
            self.weapon_mode = "spread"
            self.spread_timer = config.SPREAD_WEAPON_DURATION