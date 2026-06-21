"""Projectiles, power-ups, and weapon firing."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

import config
from ship import Ship, ShipVariant, VARIANT_STATS
from utils import Vec2, clamp, vec_add, vec_from_angle, vec_len, vec_norm, vec_scale, vec_sub


class PowerUpKind(str, Enum):
    SHIELD = "shield"
    FIRE_RATE = "fire_rate"
    SPREAD = "spread"


POWERUP_COLORS = {
    PowerUpKind.SHIELD: (100, 220, 255),
    PowerUpKind.FIRE_RATE: (255, 220, 80),
    PowerUpKind.SPREAD: (200, 120, 255),
}


def powerup_sound_name(kind: PowerUpKind) -> str:
    return f"powerup_{kind.value}"


@dataclass
class Projectile:
    position: Vec2
    velocity: Vec2
    base_damage: float
    lifetime: float
    owner_id: int
    origin: Vec2
    owner_variant: ShipVariant
    color: tuple[int, int, int] = (255, 255, 200)

    @property
    def alive(self) -> bool:
        return self.lifetime > 0

    def travel_distance(self) -> float:
        return vec_len(vec_sub(self.position, self.origin))

    def update(self, dt: float) -> None:
        self.lifetime -= dt
        self.position = vec_add(self.position, (self.velocity[0] * dt, self.velocity[1] * dt))


def projectile_speed_for_variant(variant: ShipVariant) -> float:
    if variant == ShipVariant.BALANCED:
        return config.PROJECTILE_SPEED_BALANCED
    return config.PROJECTILE_SPEED


def range_damage_multiplier(variant: ShipVariant, travel_dist: float) -> float:
    """Per-hull weapon behavior: Light close, Medium mid, Heavy long."""
    ref = max(config.PROJECTILE_RANGE_DAMAGE_REF, 1.0)
    t = clamp(travel_dist / ref, 0.0, 1.0)
    if variant == ShipVariant.LIGHT:
        close, far = config.RANGE_DAMAGE_LIGHT
        return close + (far - close) * t
    if variant == ShipVariant.HEAVY:
        close, far = config.RANGE_DAMAGE_HEAVY
        return close + (far - close) * t
    peak = config.RANGE_DAMAGE_BALANCED_PEAK
    edge = config.RANGE_DAMAGE_BALANCED_EDGE
    return edge + (peak - edge) * (1.0 - abs(t - 0.5) * 2.0)


def projectile_hit_damage(proj: Projectile) -> float:
    """Damage resolved at impact from travel distance and shooter hull."""
    mult = range_damage_multiplier(proj.owner_variant, proj.travel_distance())
    return proj.base_damage * mult


@dataclass
class PowerUp:
    kind: PowerUpKind
    position: Vec2
    lifetime: float = config.POWERUP_LIFETIME
    radius: float = 12.0
    velocity: Vec2 = (0.0, 0.0)

    @property
    def alive(self) -> bool:
        return self.lifetime > 0

    def update(self, dt: float) -> None:
        self.lifetime -= dt
        self.position = vec_add(self.position, vec_scale(self.velocity, dt))
        self.velocity = vec_scale(self.velocity, 0.94)


def fire_weapon(ship: Ship) -> list[Projectile]:
    """Create projectiles for current weapon mode."""
    if not ship.can_fire():
        return []
    ship.mark_fired()
    base_angle = ship.angle
    speed = projectile_speed_for_variant(ship.variant)
    bolt_color = (255, 255, 200)
    if ship.variant == ShipVariant.BALANCED:
        bolt_color = (140, 235, 255)
    projs: list[Projectile] = []
    muzzle = vec_add(ship.position, vec_from_angle(base_angle, ship.radius + 4))
    dmg = config.PROJECTILE_DAMAGE * VARIANT_STATS[ship.variant].get("damage_dealt_mult", 1.0)

    if ship.weapon_mode == "spread":
        for offset in [-config.SPREAD_ANGLE, 0, config.SPREAD_ANGLE]:
            angle = base_angle + offset
            projs.append(
                Projectile(
                    muzzle,
                    vec_from_angle(angle, speed),
                    dmg * 0.85,
                    config.PROJECTILE_LIFETIME,
                    ship.ship_id,
                    muzzle,
                    ship.variant,
                    bolt_color,
                )
            )
    else:
        projs.append(
            Projectile(
                muzzle,
                vec_from_angle(base_angle, speed),
                dmg,
                config.PROJECTILE_LIFETIME,
                ship.ship_id,
                muzzle,
                ship.variant,
                bolt_color,
            )
        )
    return projs


def projectile_hits_ship(proj: Projectile, ship: Ship) -> bool:
    if not ship.alive or ship.ship_id == proj.owner_id:
        return False
    return vec_len(vec_sub(proj.position, ship.position)) <= ship.radius + 2


def ships_collide(a: Ship, b: Ship) -> bool:
    if not a.alive or not b.alive:
        return False
    return vec_len(vec_sub(a.position, b.position)) <= a.radius + b.radius


def collision_impact_speed(a: Ship, b: Ship) -> float:
    rel = vec_sub(a.velocity, b.velocity)
    return vec_len(rel)


def resolve_ship_collision(a: Ship, b: Ship) -> float:
    """Separate overlapping ships and bounce. Returns pre-bounce closing speed."""
    rel_pos = vec_sub(b.position, a.position)
    dist = vec_len(rel_pos)
    min_dist = a.radius + b.radius
    if dist >= min_dist:
        return 0.0

    rel_vel = vec_sub(b.velocity, a.velocity)
    impact = vec_len(rel_vel)

    if dist < 1e-6:
        angle = random.uniform(0, 2 * math.pi)
        normal = (math.cos(angle), math.sin(angle))
        dist = 0.0
    else:
        normal = vec_norm(rel_pos)

    overlap = min_dist - dist
    mass_a = a.radius * a.radius
    mass_b = b.radius * b.radius
    total_mass = mass_a + mass_b
    a.position = (
        a.position[0] - normal[0] * overlap * (mass_b / total_mass),
        a.position[1] - normal[1] * overlap * (mass_b / total_mass),
    )
    b.position = (
        b.position[0] + normal[0] * overlap * (mass_a / total_mass),
        b.position[1] + normal[1] * overlap * (mass_a / total_mass),
    )

    vn = rel_vel[0] * normal[0] + rel_vel[1] * normal[1]
    if vn < 0:
        inv_mass_a = 1.0 / mass_a
        inv_mass_b = 1.0 / mass_b
        impulse = -(1.0 + config.SHIP_RAM_RESTITUTION) * vn
        impulse /= inv_mass_a + inv_mass_b
        a.velocity = vec_sub(a.velocity, vec_scale(normal, impulse * inv_mass_a))
        b.velocity = vec_add(b.velocity, vec_scale(normal, impulse * inv_mass_b))

    return impact


def resolve_ship_collisions(ships: list[Ship], passes: int = 2) -> None:
    for _ in range(passes):
        for i, a in enumerate(ships):
            for b in ships[i + 1 :]:
                if ships_collide(a, b):
                    resolve_ship_collision(a, b)


def random_powerup_kind() -> PowerUpKind:
    return random.choice(list(PowerUpKind))


def spawn_powerup_at(
    arena_rect: tuple[float, float, float, float],
    position: Vec2 | None = None,
) -> PowerUp:
    x, y, w, h = arena_rect
    if position is None:
        pos = (random.uniform(x + 40, x + w - 40), random.uniform(y + 40, y + h - 40))
    else:
        pos = position
    return PowerUp(random_powerup_kind(), pos)


def maybe_spawn_powerup(arena_rect: tuple[float, float, float, float]) -> PowerUp | None:
    if random.random() > config.POWERUP_SPAWN_CHANCE:
        return None
    return spawn_powerup_at(arena_rect)


def powerup_collected(powerup: PowerUp, ship: Ship) -> bool:
    if not ship.alive:
        return False
    return vec_len(vec_sub(powerup.position, ship.position)) <= ship.radius + powerup.radius