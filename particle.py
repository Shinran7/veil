"""Particle effects system."""

from __future__ import annotations

import random
from dataclasses import dataclass

from utils import Vec2, vec_add, vec_from_angle, vec_scale


@dataclass
class Particle:
    position: Vec2
    velocity: Vec2
    color: tuple[int, int, int]
    lifetime: float
    max_lifetime: float
    size: float = 2.0

    @property
    def alive(self) -> bool:
        return self.lifetime > 0

    def update(self, dt: float) -> None:
        self.lifetime -= dt
        self.position = vec_add(self.position, vec_scale(self.velocity, dt))
        self.velocity = vec_scale(self.velocity, 0.96)


class ParticleSystem:
    def __init__(self) -> None:
        self.particles: list[Particle] = []

    def emit_trail(self, pos: Vec2, angle: float, color: tuple[int, int, int]) -> None:
        vel = vec_from_angle(angle + 3.14159, random.uniform(20, 60))
        self.particles.append(
            Particle(pos, vel, color, 0.35, 0.35, size=1.5)
        )

    def emit_hit(self, pos: Vec2, color: tuple[int, int, int]) -> None:
        for _ in range(8):
            vel = vec_from_angle(random.uniform(0, 6.28), random.uniform(40, 120))
            self.particles.append(Particle(pos, vel, color, 0.4, 0.4, size=2.0))

    def emit_explosion(self, pos: Vec2) -> None:
        for _ in range(24):
            vel = vec_from_angle(random.uniform(0, 6.28), random.uniform(60, 220))
            color = (255, random.randint(180, 255), random.randint(60, 120))
            self.particles.append(Particle(pos, vel, color, 0.8, 0.8, size=3.0))

    def emit_boss_pulse(self, pos: Vec2, color: tuple[int, int, int]) -> None:
        for _ in range(18):
            vel = vec_from_angle(random.uniform(0, 6.28), random.uniform(90, 180))
            tint = tuple(min(255, int(c * 1.1)) for c in color)
            self.particles.append(Particle(pos, vel, tint, 0.45, 0.45, size=3.0))

    def emit_nebula(self, pos: Vec2) -> None:
        vel = vec_from_angle(random.uniform(0, 6.28), random.uniform(2, 8))
        color = (40, 50, 70)
        self.particles.append(Particle(pos, vel, color, random.uniform(4, 8), 8.0, size=6.0))

    def update(self, dt: float) -> None:
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]