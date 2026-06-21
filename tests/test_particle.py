"""Tests for particle module."""

from particle import Particle, ParticleSystem


def test_particle_expires() -> None:
    p = Particle((0.0, 0.0), (1.0, 0.0), (255, 255, 255), 0.1, 0.1)
    p.update(0.2)
    assert not p.alive


def test_particle_system_cleanup() -> None:
    ps = ParticleSystem()
    ps.emit_explosion((10.0, 10.0))
    assert len(ps.particles) > 0
    ps.update(2.0)
    assert len(ps.particles) == 0