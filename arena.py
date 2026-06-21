"""Arena layout, obstacles, and wave spawning."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import config
from ship import Ship, ShipVariant, pick_enemy_color
from utils import (
    Vec2,
    push_circle_out_of_circle,
    segment_circle_intersect,
    vec_add,
    vec_len,
    vec_scale,
    vec_sub,
    vec_norm,
)


@dataclass
class Obstacle:
    """Irregular asteroid — drifts slowly, exits without wrapping."""

    center: Vec2
    radius: float
    velocity: Vec2
    local_vertices: list[Vec2]
    crater_seed: int = 0

    @property
    def vertices(self) -> list[Vec2]:
        cx, cy = self.center
        return [(cx + lx, cy + ly) for lx, ly in self.local_vertices]

    @property
    def collision_radius(self) -> float:
        """Hull extent — matches the drawn polygon, not the nominal radius."""
        if not self.local_vertices:
            return self.radius
        hull = max(vec_len(v) for v in self.local_vertices)
        return max(self.radius, hull)

    def update(self, dt: float) -> None:
        self.center = vec_add(self.center, vec_scale(self.velocity, dt))

    def is_off_screen(self, rect: tuple[float, float, float, float]) -> bool:
        cx, cy = self.center
        x, y, w, h = rect
        r = self.radius
        return (
            cx + r < x
            or cx - r > x + w
            or cy + r < y
            or cy - r > y + h
        )

    @classmethod
    def _build_shape(
        cls, cx: float, cy: float, radius: float, seed: int | None = None
    ) -> tuple[list[Vec2], int]:
        rng = random.Random(seed)
        segments = rng.randint(8, 12)
        local: list[Vec2] = []
        for i in range(segments):
            angle = (2 * math.pi * i / segments) + rng.uniform(-0.25, 0.25)
            r = radius * rng.uniform(0.72, 1.12)
            local.append((math.cos(angle) * r, math.sin(angle) * r))
        crater_seed = seed if seed is not None else rng.randint(0, 99999)
        return local, crater_seed

    @classmethod
    def create(
        cls,
        cx: float,
        cy: float,
        radius: float,
        velocity: Vec2 = (0.0, 0.0),
        seed: int | None = None,
    ) -> Obstacle:
        local, crater_seed = cls._build_shape(cx, cy, radius, seed)
        return cls(
            center=(cx, cy),
            radius=radius,
            velocity=velocity,
            local_vertices=local,
            crater_seed=crater_seed,
        )

    @classmethod
    def blocking_at(cls, cx: float, cy: float, radius: float) -> Obstacle:
        """Deterministic asteroid for tests."""
        return cls.create(cx, cy, radius, seed=int(cx * 3 + cy * 7))


@dataclass
class Arena:
    rect: tuple[float, float, float, float]
    obstacles: list[Obstacle] = field(default_factory=list)
    stars: list[tuple[float, float, float, float, float, float]] = field(
        default_factory=list
    )
    _asteroid_spawn_cooldown: float = 0.0

    @classmethod
    def from_window(cls, width: int, height: int) -> Arena:
        margin = config.ARENA_MARGIN
        rect = (
            float(margin),
            float(margin),
            float(width - 2 * margin),
            float(height - 2 * margin),
        )
        stars = []
        for _ in range(120):
            base = random.uniform(0.3, 1.0)
            if random.random() < 0.38:
                phase = random.uniform(0, 6.28)
                speed = random.uniform(1.4, 4.2)
                amp = random.uniform(0.12, 0.32)
            else:
                phase = speed = amp = 0.0
            stars.append(
                (
                    random.uniform(0, width),
                    random.uniform(0, height),
                    base,
                    phase,
                    speed,
                    amp,
                )
            )
        return cls(rect=rect, stars=stars)

    def spawn_point(self, edge: int | None = None) -> Vec2:
        x, y, w, h = self.rect
        edge = edge if edge is not None else random.randint(0, 3)
        if edge == 0:
            return (x + 20, random.uniform(y + 20, y + h - 20))
        if edge == 1:
            return (x + w - 20, random.uniform(y + 20, y + h - 20))
        if edge == 2:
            return (random.uniform(x + 20, x + w - 20), y + 20)
        return (random.uniform(x + 20, x + w - 20), y + h - 20)

    def spawn_point_inner(self, inset_frac: float | None = None) -> Vec2:
        """Spawn inside the main play area — avoids edge-clustered AI brawls."""
        inset = (
            inset_frac
            if inset_frac is not None
            else config.ARENA_SPAWN_INSET_FRAC
        )
        x, y, w, h = self.rect
        pad_x = w * inset
        pad_y = h * inset
        return (
            random.uniform(x + pad_x, x + w - pad_x),
            random.uniform(y + pad_y, y + h - pad_y),
        )

    def enemy_count_for_wave(self, wave: int) -> int:
        base = config.WAVE_ENEMY_BASE + (wave - 1) * config.WAVE_ENEMY_PER_WAVE
        jitter = random.randint(-config.WAVE_ENEMY_JITTER, config.WAVE_ENEMY_JITTER)
        return max(2, min(config.WAVE_ENEMY_MAX, base + jitter))

    def player_spawn_point(self) -> Vec2:
        x, y, w, h = self.rect
        return (x + w * 0.5, y + h * 0.5)

    def spawn_enemy_positions(self, count: int, avoid: Vec2) -> list[Vec2]:
        positions: list[Vec2] = []
        for i in range(count):
            placed = False
            for edge in (1, 3, 0, 2, None):
                for _ in range(12):
                    pos = self.spawn_point(edge) if edge is not None else self.spawn_point()
                    if vec_len(vec_sub(pos, avoid)) < config.SPAWN_MIN_DISTANCE:
                        continue
                    if any(vec_len(vec_sub(pos, other)) < 70 for other in positions):
                        continue
                    positions.append(pos)
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                positions.append(self.spawn_point(1 if i % 2 else 3))
        return positions

    def spawn_enemies(
        self, wave: int, next_id: int, avoid: Vec2 | None = None
    ) -> tuple[list[Ship], int]:
        count = self.enemy_count_for_wave(wave)
        avoid_pos = avoid or self.player_spawn_point()
        positions = self.spawn_enemy_positions(count, avoid_pos)
        ships: list[Ship] = []
        variants = list(ShipVariant)
        for pos in positions:
            variant = random.choice(variants)
            ship = Ship.create(
                variant,
                pos,
                angle=random.uniform(0, 6.28),
                ship_id=next_id,
                enemy_color=pick_enemy_color(),
            )
            ship.ai_controlled = True
            ships.append(ship)
            next_id += 1
        return ships, next_id

    def _drift_speed(self) -> float:
        return random.uniform(config.ASTEROID_DRIFT_MIN, config.ASTEROID_DRIFT_MAX)

    def _spawn_asteroid_from_edge(self) -> Obstacle:
        x, y, w, h = self.rect
        mid = (x + w * 0.5, y + h * 0.5)
        radius = random.uniform(28, 48)
        speed = self._drift_speed()
        edge = random.randint(0, 3)
        margin = radius + 16
        if edge == 0:
            cx = x - margin
            cy = random.uniform(y + radius, y + h - radius)
        elif edge == 1:
            cx = x + w + margin
            cy = random.uniform(y + radius, y + h - radius)
        elif edge == 2:
            cx = random.uniform(x + radius, x + w - radius)
            cy = y - margin
        else:
            cx = random.uniform(x + radius, x + w - radius)
            cy = y + h + margin
        toward = vec_norm(vec_sub(mid, (cx, cy)))
        aim = math.atan2(toward[1], toward[0]) + random.uniform(-0.4, 0.4)
        vel = (math.cos(aim) * speed, math.sin(aim) * speed)
        return Obstacle.create(cx, cy, radius, velocity=vel)

    def init_asteroid_field(self, count: int | None = None) -> None:
        """Seed drifting asteroids just off-screen; they roll in from the edges."""
        self.obstacles.clear()
        if count is not None:
            total = count
        else:
            total = random.randint(config.ASTEROID_MIN_COUNT, config.ASTEROID_MAX_COUNT)
        for _ in range(total):
            self.obstacles.append(self._spawn_asteroid_from_edge())
        self._asteroid_spawn_cooldown = random.uniform(1.0, 3.0)

    def _try_spawn_asteroid(self) -> None:
        if len(self.obstacles) >= config.ASTEROID_MAX_COUNT:
            return
        self.obstacles.append(self._spawn_asteroid_from_edge())
        self._asteroid_spawn_cooldown = random.uniform(
            config.ASTEROID_SPAWN_MIN_INTERVAL, config.ASTEROID_SPAWN_MAX_INTERVAL
        )

    def _separate_obstacle_pair(self, a: Obstacle, b: Obstacle) -> None:
        rel = vec_sub(b.center, a.center)
        dist = vec_len(rel)
        min_dist = a.collision_radius + b.collision_radius
        if dist >= min_dist:
            return
        if dist < 1e-6:
            angle = random.uniform(0, 2 * math.pi)
            normal = (math.cos(angle), math.sin(angle))
            dist = 0.0
        else:
            normal = vec_norm(rel)
        overlap = min_dist - dist
        mass_a = a.collision_radius * a.collision_radius
        mass_b = b.collision_radius * b.collision_radius
        total_mass = mass_a + mass_b
        a.center = (
            a.center[0] - normal[0] * overlap * (mass_b / total_mass),
            a.center[1] - normal[1] * overlap * (mass_b / total_mass),
        )
        b.center = (
            b.center[0] + normal[0] * overlap * (mass_a / total_mass),
            b.center[1] + normal[1] * overlap * (mass_a / total_mass),
        )
        rel_vel = vec_sub(b.velocity, a.velocity)
        vn = rel_vel[0] * normal[0] + rel_vel[1] * normal[1]
        if vn >= 0:
            return
        inv_mass_a = 1.0 / mass_a
        inv_mass_b = 1.0 / mass_b
        impulse = -vn * 0.85
        impulse /= inv_mass_a + inv_mass_b
        a.velocity = vec_sub(a.velocity, vec_scale(normal, impulse * inv_mass_a))
        b.velocity = vec_add(b.velocity, vec_scale(normal, impulse * inv_mass_b))

    def resolve_obstacle_collisions(self, passes: int = 4) -> None:
        for _ in range(passes):
            for i, a in enumerate(self.obstacles):
                for b in self.obstacles[i + 1 :]:
                    self._separate_obstacle_pair(a, b)

    def update_asteroids(self, dt: float) -> None:
        """Drift asteroids; remove off-screen; keep a visible minimum on screen."""
        for obs in self.obstacles:
            obs.update(dt)
        self.resolve_obstacle_collisions()
        self.obstacles = [o for o in self.obstacles if not o.is_off_screen(self.rect)]

        while len(self.obstacles) < config.ASTEROID_MIN_COUNT:
            self.obstacles.append(self._spawn_asteroid_from_edge())
            self._asteroid_spawn_cooldown = random.uniform(1.0, 2.5)
        self.resolve_obstacle_collisions()

        if len(self.obstacles) >= config.ASTEROID_MAX_COUNT:
            return

        self._asteroid_spawn_cooldown -= dt
        if self._asteroid_spawn_cooldown > 0:
            return
        if random.random() > config.ASTEROID_SPAWN_CHANCE:
            self._asteroid_spawn_cooldown = random.uniform(1.0, 2.5)
            return
        self._try_spawn_asteroid()
        self.resolve_obstacle_collisions()

    def ship_hits_obstacle(self, ship: Ship) -> bool:
        for obs in self.obstacles:
            if vec_len(vec_sub(ship.position, obs.center)) <= ship.radius + obs.collision_radius:
                return True
        return False

    def resolve_powerup_obstacle_collisions(self, powerups: list) -> None:
        for pu in powerups:
            if not pu.alive:
                continue
            for obs in self.obstacles:
                if vec_len(vec_sub(pu.position, obs.center)) > pu.radius + obs.collision_radius:
                    continue
                old_pos = pu.position
                pu.position = push_circle_out_of_circle(
                    pu.position, pu.radius, obs.center, obs.collision_radius
                )
                nudge = vec_sub(pu.position, old_pos)
                if vec_len(nudge) > 0.05:
                    normal = vec_norm(nudge)
                    pu.velocity = vec_add(
                        pu.velocity,
                        (
                            obs.velocity[0] * 0.42 + normal[0] * 20.0,
                            obs.velocity[1] * 0.42 + normal[1] * 20.0,
                        ),
                    )

    def resolve_obstacle_collision(self, ship: Ship) -> None:
        from utils import vec_norm

        for obs in self.obstacles:
            if vec_len(vec_sub(ship.position, obs.center)) > ship.radius + obs.collision_radius:
                continue
            old_pos = ship.position
            ship.position = push_circle_out_of_circle(
                ship.position, ship.radius, obs.center, obs.collision_radius
            )
            nudge = vec_sub(ship.position, old_pos)
            if vec_len(nudge) > 0.5:
                normal = vec_norm(nudge)
                vn = ship.velocity[0] * normal[0] + ship.velocity[1] * normal[1]
                if vn < 0:
                    ship.velocity = (
                        ship.velocity[0] - normal[0] * vn * 1.4,
                        ship.velocity[1] - normal[1] * vn * 1.4,
                    )
            else:
                ship.velocity = (ship.velocity[0] * 0.3, ship.velocity[1] * 0.3)

    def projectile_hits_obstacle(self, start: Vec2, end: Vec2) -> bool:
        for obs in self.obstacles:
            if segment_circle_intersect(start, end, obs.center, obs.collision_radius + 2):
                return True
        return False