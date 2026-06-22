"""AI ship controller."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

import config
from combat import PowerUpKind, projectile_speed_for_variant, range_damage_multiplier
from ship import Ship, ShipVariant
from utils import (
    Vec2,
    segment_circle_intersect,
    vec_add,
    vec_from_angle,
    vec_len,
    vec_norm,
    vec_scale,
    vec_sub,
    wrapped_delta,
    wrapped_distance,
)


class Personality(str, Enum):
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    FLANKER = "flanker"


class PilotArchetype(str, Enum):
    HUNTER = "hunter"
    SURVIVOR = "survivor"
    BRUISER = "bruiser"
    FLANKER = "flanker"
    OPPORTUNIST = "opportunist"


@dataclass(frozen=True)
class PilotProfile:
    """Per-ship tactical tendencies — weights scale tactic eligibility and thrust."""

    archetype: PilotArchetype
    tail_hold: float = 1.0
    six_evade: float = 1.0
    reverse_gun: float = 1.0
    powerup_greed: float = 1.0
    risk_tolerance: float = 1.0
    kite_retreat: float = 1.0
    heavy_commit: float = 1.0
    flank_strafe: float = 1.0
    chase_push: float = 1.0


NEUTRAL_PROFILE = PilotProfile(archetype=PilotArchetype.HUNTER)

ARCHETYPE_PROFILES: dict[PilotArchetype, PilotProfile] = {
    PilotArchetype.HUNTER: PilotProfile(
        archetype=PilotArchetype.HUNTER,
        tail_hold=1.45,
        chase_push=1.2,
        risk_tolerance=1.15,
        kite_retreat=0.72,
        six_evade=0.88,
    ),
    PilotArchetype.SURVIVOR: PilotProfile(
        archetype=PilotArchetype.SURVIVOR,
        six_evade=1.42,
        kite_retreat=1.38,
        risk_tolerance=0.72,
        tail_hold=0.82,
        chase_push=0.82,
        powerup_greed=0.9,
    ),
    PilotArchetype.BRUISER: PilotProfile(
        archetype=PilotArchetype.BRUISER,
        reverse_gun=1.55,
        heavy_commit=1.45,
        chase_push=1.28,
        risk_tolerance=1.22,
        tail_hold=1.05,
        kite_retreat=0.78,
    ),
    PilotArchetype.FLANKER: PilotProfile(
        archetype=PilotArchetype.FLANKER,
        flank_strafe=1.55,
        kite_retreat=1.12,
        tail_hold=0.88,
        chase_push=0.95,
        six_evade=1.08,
    ),
    PilotArchetype.OPPORTUNIST: PilotProfile(
        archetype=PilotArchetype.OPPORTUNIST,
        powerup_greed=1.58,
        risk_tolerance=0.92,
        chase_push=0.9,
        tail_hold=0.92,
    ),
}

ARCHETYPE_TO_PERSONALITY = {
    PilotArchetype.HUNTER: Personality.AGGRESSIVE,
    PilotArchetype.BRUISER: Personality.AGGRESSIVE,
    PilotArchetype.OPPORTUNIST: Personality.AGGRESSIVE,
    PilotArchetype.SURVIVOR: Personality.DEFENSIVE,
    PilotArchetype.FLANKER: Personality.FLANKER,
}

VARIANT_ARCHETYPE_POOL: dict[ShipVariant, tuple[PilotArchetype, ...]] = {
    ShipVariant.LIGHT: (
        PilotArchetype.HUNTER,
        PilotArchetype.FLANKER,
        PilotArchetype.OPPORTUNIST,
        PilotArchetype.HUNTER,
    ),
    ShipVariant.BALANCED: (
        PilotArchetype.HUNTER,
        PilotArchetype.BRUISER,
        PilotArchetype.FLANKER,
        PilotArchetype.OPPORTUNIST,
    ),
    ShipVariant.HEAVY: (
        PilotArchetype.BRUISER,
        PilotArchetype.SURVIVOR,
        PilotArchetype.BRUISER,
        PilotArchetype.SURVIVOR,
    ),
}

PERSONALITY_FOR_VARIANT = {
    ShipVariant.LIGHT: Personality.AGGRESSIVE,
    ShipVariant.BALANCED: Personality.AGGRESSIVE,
    ShipVariant.HEAVY: Personality.DEFENSIVE,
}


def profile_for_ship(ship: Ship) -> PilotProfile:
    pool = VARIANT_ARCHETYPE_POOL.get(ship.variant, (PilotArchetype.HUNTER,))
    archetype = pool[ship.ship_id % len(pool)]
    return ARCHETYPE_PROFILES[archetype]

VARIANT_TIER = {
    ShipVariant.LIGHT: 0,
    ShipVariant.BALANCED: 1,
    ShipVariant.HEAVY: 2,
}


@dataclass
class TargetMotionTrack:
    last_velocity: Vec2 = (0.0, 0.0)
    last_angular_velocity: float = 0.0
    velocity_delta: Vec2 = (0.0, 0.0)
    angular_accel: float = 0.0
    initialized: bool = False


@dataclass
class CombatSituation:
    """Per-tick battlefield facts — perception only, before aim/thrust/fire."""

    ship: Ship
    target: Ship
    opponents: list[Ship]
    obstacles: list
    powerups: list
    arena_rect: tuple[float, float, float, float] | None
    rel_to_target: Vec2
    dist: float
    closing: float
    has_los: bool
    engage_quality: float
    behind_target: bool
    shot_bearing: float
    misaligned_shot: bool
    target_bearing: float
    rear_threat: Ship | None
    being_tailed: bool
    rear_dist: float
    caution: float
    shield_ramming: bool
    panic_pull: bool
    panicking: bool
    panic_snap: bool
    pickup: tuple | None
    seeking_powerup: bool
    pickup_bias: float
    pickup_field_risk: float
    tail_gunner: bool
    six_evade: bool
    reverse_gun: bool
    reverse_eligible: bool
    kiting: bool
    snap_shot: bool
    reengage: bool
    heavy_duel: bool
    solo_dogfight: bool
    center_bias_scale: float


@dataclass
class AIDecisionContext:
    """Snapshot of AI reasoning for one tick — used by telemetry."""

    mode: str = "wander"
    archetype: str | None = None
    target_id: int | None = None
    target_dist: float = 0.0
    caution: float = 0.0
    behind_target: bool = False
    tail_gunner: bool = False
    being_tailed: bool = False
    six_evade: bool = False
    reverse_gun: bool = False
    panicking: bool = False
    kiting: bool = False
    shield_ramming: bool = False
    seeking_powerup: bool = False
    breaking_orbit: bool = False
    heavy_duel: bool = False
    engage_quality: float = 0.0
    rotate: float = 0.0
    thrust: float = 0.0
    fired: bool = False


class AIController:
    def __init__(
        self,
        personality: Personality | None = None,
        profile: PilotProfile | None = None,
    ) -> None:
        self.profile = profile or NEUTRAL_PROFILE
        self.personality = (
            personality
            or ARCHETYPE_TO_PERSONALITY.get(self.profile.archetype)
            or random.choice(list(Personality))
        )
        self.wander_timer = 0.0
        self.stuck_timer = 0.0
        self.flank_sign = random.choice([-1.0, 1.0])
        self.chase_stale_timer = 0.0
        self.lead_stale_timer = 0.0
        self.orbit_stale_timer = 0.0
        self.orbit_break_timer = 0.0
        self.break_orbit_sign = random.choice([-1.0, 1.0])
        self.jitter_timer = 0.0
        self.kite_burst_timer = 0.0
        self.panic_burst_timer = 0.0
        self.last_dist = 0.0
        self.locked_target_id: int | None = None
        self.heavy_duel_stale_timer = 0.0
        self.heavy_duel_commit_timer = 0.0
        self.reverse_gun_eligible_timer = 0.0
        self.reverse_gun_commit_timer = 0.0
        self.reverse_gun_cooldown = 0.0
        self._target_tracks: dict[int, TargetMotionTrack] = {}
        self.last_context = AIDecisionContext()
        self.last_situation: CombatSituation | None = None

    @classmethod
    def for_ship(cls, ship: Ship) -> AIController:
        profile = profile_for_ship(ship)
        personality = ARCHETYPE_TO_PERSONALITY[profile.archetype]
        ctrl = cls(personality, profile=profile)
        ctrl.break_orbit_sign = 1.0 if ship.ship_id % 2 == 0 else -1.0
        return ctrl

    def _path_near_ships(
        self,
        start: Vec2,
        end: Vec2,
        ships: list[Ship],
        clearance: float = 72.0,
    ) -> bool:
        steps = 6
        for other in ships:
            for i in range(1, steps + 1):
                t = i / steps
                sample = (
                    start[0] + (end[0] - start[0]) * t,
                    start[1] + (end[1] - start[1]) * t,
                )
                if (
                    vec_len(vec_sub(sample, other.position))
                    < other.radius + clearance
                ):
                    return True
        return False

    def _powerup_field_risk(
        self,
        ship: Ship,
        pu,
        others: list[Ship],
        arena_rect: tuple[float, float, float, float] | None,
    ) -> float:
        opponents = self._living_opponents(ship, others)
        if not opponents:
            return 0.0

        risk = 0.0
        if len(opponents) >= 2:
            risk += 0.20
        if len(opponents) >= 3:
            risk += 0.14

        for other in opponents:
            if arena_rect is not None:
                to_pickup = wrapped_distance(
                    other.position, pu.position, arena_rect
                )
                to_ship = wrapped_distance(
                    ship.position, other.position, arena_rect
                )
            else:
                to_pickup = vec_len(vec_sub(pu.position, other.position))
                to_ship = vec_len(vec_sub(other.position, ship.position))
            if to_pickup < 110:
                risk += 0.30
            elif to_pickup < 190:
                risk += 0.14
            if to_ship < 140:
                risk += 0.20
            elif to_ship < 220:
                risk += 0.10

        if self._path_near_ships(ship.position, pu.position, opponents):
            risk += 0.24

        return min(1.0, risk)

    def _best_powerup_target(
        self,
        ship: Ship,
        powerups: list,
        threat_dist: float,
        caution: float,
        obstacles: list,
        others: list[Ship] | None = None,
        arena_rect: tuple[float, float, float, float] | None = None,
    ) -> tuple | None:
        best: tuple | None = None
        best_score = 0.0
        for pu in powerups:
            if not pu.alive:
                continue
            pu_dist = vec_len(vec_sub(pu.position, ship.position))
            score = self._powerup_seek_score(
                ship, pu, pu_dist, threat_dist, caution, obstacles
            )
            if others:
                field_risk = self._powerup_field_risk(
                    ship, pu, others, arena_rect
                )
                score = max(0.0, score - field_risk * config.AI_POWERUP_RISK_PENALTY)
            if score > best_score:
                best_score = score
                best = (pu, pu_dist, score)
        return best

    def _powerup_seek_score(
        self,
        ship: Ship,
        pu,
        pu_dist: float,
        threat_dist: float,
        caution: float,
        obstacles: list,
    ) -> float:
        if pu_dist > 380:
            return 0.0
        score = max(0.0, 1.0 - pu_dist / 380.0) * 0.45

        if threat_dist > 320:
            score += 0.42
        elif threat_dist > 230:
            score += 0.26
        elif threat_dist > 170:
            score += 0.1
        elif threat_dist < 130:
            score -= 0.38

        if pu_dist < 120 and threat_dist > 170:
            score += 0.34
        if pu_dist < 70 and threat_dist > 140:
            score += 0.22

        hurt = ship.health < ship.max_health * 0.55
        if caution > 0.55 and pu_dist > 100 and not (hurt and pu.kind == PowerUpKind.SHIELD):
            score -= 0.18
        elif caution < 0.3:
            score += 0.08

        if pu.kind == PowerUpKind.SHIELD and ship.shield_timer < 1.5:
            score += 0.32
        if ship.champion_wins >= 2 and pu.kind == PowerUpKind.SHIELD:
            score += 0.28
        elif pu.kind == PowerUpKind.FIRE_RATE:
            score += 0.16
        elif pu.kind == PowerUpKind.SPREAD:
            score += 0.2

        if hurt and pu.kind == PowerUpKind.SHIELD:
            score += 0.22
            if pu_dist < 200:
                score += 0.35
            if pu_dist < 90:
                score += 0.3

        if self._path_blocked(ship.position, pu.position, obstacles, clearance=10):
            score -= 0.22
        else:
            score += 0.12

        return max(0.0, score)

    def _arena_center(
        self, arena_rect: tuple[float, float, float, float]
    ) -> Vec2:
        x, y, w, h = arena_rect
        return (x + w * 0.5, y + h * 0.5)

    def _edge_proximity(
        self, pos: Vec2, arena_rect: tuple[float, float, float, float]
    ) -> float:
        """0 in the inner band, 1 hugging the arena wall."""
        x, y, w, h = arena_rect
        margin = min(w, h) * config.AI_ARENA_EDGE_MARGIN_FRAC
        nearest = min(pos[0] - x, x + w - pos[0], pos[1] - y, y + h - pos[1])
        if nearest >= margin:
            return 0.0
        return 1.0 - nearest / margin

    def _bias_aim_toward_center(
        self,
        ship: Ship,
        aim_pos: Vec2,
        arena_rect: tuple[float, float, float, float] | None,
        bias_scale: float = 1.0,
    ) -> Vec2:
        if arena_rect is None:
            return aim_pos
        edge = self._edge_proximity(ship.position, arena_rect)
        if edge <= 0.02:
            return aim_pos
        center = self._arena_center(arena_rect)
        bias = edge * config.AI_ARENA_CENTER_BIAS_MAX * bias_scale
        return (
            aim_pos[0] * (1.0 - bias) + center[0] * bias,
            aim_pos[1] * (1.0 - bias) + center[1] * bias,
        )

    def _is_heavy_duel(self, ship: Ship, target: Ship, opponents: list[Ship]) -> bool:
        return (
            len(opponents) == 1
            and ship.variant == ShipVariant.HEAVY
            and target.variant == ShipVariant.HEAVY
        )

    def _steer_from_aim(self, ship: Ship, aim_pos: Vec2) -> tuple[float, float, float]:
        dx = aim_pos[0] - ship.position[0]
        dy = aim_pos[1] - ship.position[1]
        desired = math.atan2(dy, dx)
        angle_diff = self._angle_diff(ship.angle, desired)
        rotate_dir = self._rotate_toward_diff(angle_diff)
        return angle_diff, rotate_dir, desired

    def _rotate_toward_diff(self, angle_diff: float, gate: float = 0.15) -> float:
        if angle_diff > gate:
            return 1.0
        if angle_diff < -gate:
            return -1.0
        return 0.0

    def _bearing_to(self, ship: Ship, pos: Vec2) -> float:
        dx = pos[0] - ship.position[0]
        dy = pos[1] - ship.position[1]
        return math.atan2(dy, dx)

    def _shot_alignment_bearing(
        self, ship: Ship, target: Ship, rel: Vec2
    ) -> float:
        return abs(self._angle_diff(ship.angle, math.atan2(rel[1], rel[0])))

    def _update_target_track(self, target: Ship, dt: float) -> None:
        track = self._target_tracks.get(target.ship_id)
        if track is None or not track.initialized:
            self._target_tracks[target.ship_id] = TargetMotionTrack(
                last_velocity=target.velocity,
                last_angular_velocity=target.angular_velocity,
                initialized=True,
            )
            return
        if dt <= 0.0:
            return
        inv_dt = 1.0 / dt
        raw_accel = (
            (target.velocity[0] - track.last_velocity[0]) * inv_dt,
            (target.velocity[1] - track.last_velocity[1]) * inv_dt,
        )
        blend = config.AI_PREDICT_ACCEL_BLEND
        track.velocity_delta = (
            track.velocity_delta[0] * (1.0 - blend) + raw_accel[0] * blend,
            track.velocity_delta[1] * (1.0 - blend) + raw_accel[1] * blend,
        )
        raw_ang_accel = (target.angular_velocity - track.last_angular_velocity) * inv_dt
        track.angular_accel = track.angular_accel * (1.0 - blend) + raw_ang_accel * blend
        track.last_velocity = target.velocity
        track.last_angular_velocity = target.angular_velocity

    def _clamp_predicted_accel(self, accel: Vec2) -> Vec2:
        mag = vec_len(accel)
        cap = config.AI_PREDICT_MAX_ACCEL
        if mag <= cap or mag < 1e-6:
            return accel
        scale = cap / mag
        return (accel[0] * scale, accel[1] * scale)

    def _predict_target_position(
        self,
        target: Ship,
        horizon: float,
        observer_variant: ShipVariant,
    ) -> Vec2:
        if horizon <= 0.0:
            return target.position
        track = self._target_tracks.get(target.ship_id)
        pos = target.position
        vel = target.velocity
        accel = (0.0, 0.0)
        if track is not None and track.initialized:
            accel = self._clamp_predicted_accel(track.velocity_delta)
        pred = (
            pos[0] + vel[0] * horizon + 0.5 * accel[0] * horizon * horizon,
            pos[1] + vel[1] * horizon + 0.5 * accel[1] * horizon * horizon,
        )
        ang_vel = target.angular_velocity
        if abs(ang_vel) > 0.12:
            speed = vec_len(vel)
            if speed > 18.0:
                future_angle = (
                    target.angle
                    + ang_vel * horizon * 0.9
                    + 0.5 * (track.angular_accel if track else 0.0) * horizon * horizon * 0.35
                )
                turned = vec_from_angle(future_angle, speed)
                turn_blend = min(
                    config.AI_PREDICT_TURN_BLEND_MAX,
                    abs(ang_vel) * horizon * config.AI_PREDICT_TURN_SENSITIVITY,
                )
                if (
                    observer_variant == ShipVariant.HEAVY
                    or target.variant == ShipVariant.HEAVY
                ):
                    turn_blend = min(
                        config.AI_PREDICT_TURN_BLEND_MAX,
                        turn_blend * config.AI_PREDICT_HEAVY_TURN_MULT,
                    )
                blended_vel = (
                    vel[0] * (1.0 - turn_blend) + turned[0] * turn_blend,
                    vel[1] * (1.0 - turn_blend) + turned[1] * turn_blend,
                )
                pred = (
                    pos[0]
                    + blended_vel[0] * horizon
                    + 0.5 * accel[0] * horizon * horizon * 0.65,
                    pos[1]
                    + blended_vel[1] * horizon
                    + 0.5 * accel[1] * horizon * horizon * 0.65,
                )
        return pred

    def _aim_when_behind(
        self,
        ship: Ship,
        target: Ship,
        rel: Vec2,
        arena_rect: tuple[float, float, float, float] | None,
        misaligned: bool,
    ) -> Vec2:
        """Prefer a short turn to the target; only lead when already lined up."""
        if misaligned:
            horizon = min(
                config.AI_PREDICT_AIM_HORIZON_MAX,
                self._shot_alignment_bearing(ship, target, rel) * 0.14,
            )
            return self._predict_target_position(target, horizon, ship.variant)
        lead = self.lead_target(ship, target, arena_rect)
        lead_bearing = self._bearing_to(ship, lead)
        direct_bearing = math.atan2(rel[1], rel[0])
        if abs(self._angle_diff(ship.angle, lead_bearing)) <= (
            abs(self._angle_diff(ship.angle, direct_bearing)) + 0.12
        ):
            return lead
        return target.position

    def _target_delta(
        self,
        ship: Ship,
        target: Ship,
        arena_rect: tuple[float, float, float, float] | None,
    ) -> Vec2:
        if arena_rect is None:
            return vec_sub(target.position, ship.position)
        raw = vec_sub(target.position, ship.position)
        wrapped = wrapped_delta(ship.position, target.position, arena_rect)
        edge = self._edge_proximity(ship.position, arena_rect)
        target_edge = self._edge_proximity(target.position, arena_rect)
        if (
            (edge > config.AI_ARENA_WRAP_CHASE_EDGE or target_edge > config.AI_ARENA_WRAP_CHASE_EDGE)
            and vec_len(wrapped) < vec_len(raw) * 0.82
        ):
            return raw
        return wrapped

    def nearest_threat(
        self,
        ship: Ship,
        others: list[Ship],
        arena_rect: tuple[float, float, float, float] | None = None,
    ) -> Ship | None:
        best: Ship | None = None
        best_dist = float("inf")
        for other in others:
            if other is ship or not other.alive:
                continue
            if arena_rect is not None:
                dist = wrapped_distance(ship.position, other.position, arena_rect)
            else:
                dist = vec_len(vec_sub(other.position, ship.position))
            if dist < best_dist:
                best_dist = dist
                best = other
        return best

    def _living_opponents(self, ship: Ship, others: list[Ship]) -> list[Ship]:
        return [o for o in others if o.alive and o.ship_id != ship.ship_id]

    def _score_combat_target(
        self,
        ship: Ship,
        other: Ship,
        arena_rect: tuple[float, float, float, float] | None,
        obstacles: list,
    ) -> float:
        rel = self._target_delta(ship, other, arena_rect)
        dist = vec_len(rel)
        if dist > config.AI_TARGET_MAX_DIST:
            return 0.0

        score = max(0.0, 1.0 - dist / config.AI_TARGET_MAX_DIST) * 0.30

        to_other = math.atan2(rel[1], rel[0])
        bearing = abs(self._angle_diff(ship.angle, to_other))
        if bearing < 0.25:
            score += 0.44
        elif bearing < 0.55:
            score += 0.30
        elif bearing < 0.95:
            score += 0.12
        else:
            score -= 0.10

        if self._in_weapon_sweet_spot(ship, dist):
            score += 0.24

        lead = self.lead_target(ship, other, arena_rect)
        lead_rel = vec_sub(lead, ship.position)
        lead_bearing = abs(
            self._angle_diff(ship.angle, math.atan2(lead_rel[1], lead_rel[0]))
        )
        if lead_bearing < 0.32:
            score += 0.16

        health_ratio = other.health / other.max_health
        if health_ratio < 0.30:
            score += 0.22
        elif health_ratio < 0.50:
            score += 0.10

        if not self._path_blocked(ship.position, other.position, obstacles, clearance=12.0):
            score += 0.08

        if self._is_behind_target(ship, other, rel):
            score += config.AI_TAIL_TARGET_BONUS

        return max(0.0, score)

    def _select_combat_target(
        self,
        ship: Ship,
        others: list[Ship],
        obstacles: list,
        arena_rect: tuple[float, float, float, float] | None = None,
    ) -> Ship | None:
        best: Ship | None = None
        best_score = -1.0
        for other in self._living_opponents(ship, others):
            score = self._score_combat_target(ship, other, arena_rect, obstacles)
            if score > best_score:
                best_score = score
                best = other
        if best is None:
            self.locked_target_id = None
            return None

        if self.locked_target_id is not None:
            locked = next(
                (
                    o
                    for o in self._living_opponents(ship, others)
                    if o.ship_id == self.locked_target_id
                ),
                None,
            )
            if locked is not None:
                locked_score = self._score_combat_target(
                    ship, locked, arena_rect, obstacles
                )
                margin = config.AI_TARGET_SWITCH_MARGIN
                locked_rel = self._target_delta(ship, locked, arena_rect)
                if self._is_behind_target(ship, locked, locked_rel):
                    margin += config.AI_TAIL_TARGET_LOCK_MARGIN
                if locked_score >= best_score - margin:
                    return locked

        self.locked_target_id = best.ship_id
        return best

    def _engagement_quality(
        self,
        ship: Ship,
        target: Ship,
        dist: float,
        rel: Vec2,
        obstacles: list,
        arena_rect: tuple[float, float, float, float] | None = None,
    ) -> float:
        to_target = math.atan2(rel[1], rel[0])
        bearing = abs(self._angle_diff(ship.angle, to_target))
        quality = 0.0
        if bearing < 0.28:
            quality += 0.38
        elif bearing < 0.58:
            quality += 0.22
        elif bearing < 0.95:
            quality += 0.08

        if self._in_weapon_sweet_spot(ship, dist):
            quality += 0.30

        ideal = self._ideal_weapon_range(ship)
        band = config.AI_RANGE_INNER_TOLERANCE
        if abs(dist - ideal) < band:
            quality += 0.22
        elif abs(dist - ideal) < band * 1.6:
            quality += 0.10

        if not self._path_blocked(ship.position, target.position, obstacles, clearance=12.0):
            quality += 0.10

        lead = self.lead_target(ship, target, arena_rect)
        lead_rel = vec_sub(lead, ship.position)
        lead_bearing = abs(
            self._angle_diff(ship.angle, math.atan2(lead_rel[1], lead_rel[0]))
        )
        if lead_bearing < 0.35:
            quality += 0.12

        return min(1.0, quality)

    def lead_target(
        self,
        shooter: Ship,
        target: Ship,
        arena_rect: tuple[float, float, float, float] | None = None,
    ) -> Vec2:
        rel = self._target_delta(shooter, target, arena_rect)
        dist = vec_len(rel)
        if dist < 1:
            return target.position
        bullet_time = dist / projectile_speed_for_variant(shooter.variant)
        return self._predict_target_position(target, bullet_time, shooter.variant)

    def _is_behind_target(self, ship: Ship, target: Ship, rel: Vec2) -> bool:
        """True when ship sits in the target's rear arc (safe tail shot)."""
        dist = vec_len(rel)
        if dist > 420 or dist < 35:
            return False
        to_ship = math.atan2(-rel[1], -rel[0])
        rear_gap = abs(self._angle_diff(target.angle, to_ship))
        return rear_gap > 2.2

    def _nearest_rear_threat(
        self,
        ship: Ship,
        others: list[Ship],
        arena_rect: tuple[float, float, float, float] | None,
    ) -> Ship | None:
        """Nearest opponent sitting on this ship's six."""
        best: Ship | None = None
        best_dist = float("inf")
        for other in self._living_opponents(ship, others):
            rel = self._target_delta(other, ship, arena_rect)
            if not self._is_behind_target(other, ship, rel):
                continue
            dist = vec_len(rel)
            if dist < best_dist:
                best_dist = dist
                best = other
        return best

    def _reverse_gun_eligible(
        self,
        ship: Ship,
        target: Ship,
        dist: float,
        rel: Vec2,
        closing: float,
        behind_target: bool,
        has_los: bool,
    ) -> bool:
        """Head-on, in range, closing — worth considering astern gun run."""
        if behind_target or not has_los:
            return False
        if dist < config.AI_REVERSE_GUN_MIN_DIST or dist > config.AI_REVERSE_GUN_MAX_DIST:
            return False
        to_target = math.atan2(rel[1], rel[0])
        if abs(self._angle_diff(ship.angle, to_target)) > config.AI_REVERSE_GUN_BEARING:
            return False
        ideal = self._ideal_weapon_range(ship)
        inner = config.AI_RANGE_INNER_TOLERANCE
        too_close = dist < ideal - inner * 0.35
        if closing >= config.AI_REVERSE_GUN_CLOSING:
            return True
        return too_close and closing > 12.0

    def _reverse_gun_thrust(self, ship: Ship, commit_remaining: float) -> float:
        """Ramp into reverse instead of slamming from cruise to full astern."""
        elapsed = config.AI_REVERSE_GUN_COMMIT - commit_remaining
        ramp = min(1.0, max(0.0, elapsed / config.AI_REVERSE_GUN_RAMP_TIME))
        thrust = config.AI_REVERSE_GUN_THRUST_MIN + (
            config.AI_REVERSE_GUN_THRUST_MAX - config.AI_REVERSE_GUN_THRUST_MIN
        ) * ramp
        speed = vec_len(ship.velocity)
        if speed > 210:
            thrust = min(thrust, config.AI_REVERSE_GUN_THRUST_MIN)
        return thrust

    def _break_six_aim(
        self,
        ship: Ship,
        chaser: Ship,
        arena_rect: tuple[float, float, float, float] | None,
    ) -> Vec2:
        """Jink off the chaser's line — face them if blind, otherwise hard break."""
        rel = self._target_delta(ship, chaser, arena_rect)
        dist = max(vec_len(rel), 1.0)
        to_chaser = math.atan2(rel[1], rel[0])
        if abs(self._angle_diff(ship.angle, to_chaser)) > 1.05:
            return chaser.position
        perp = (-rel[1] / dist * self.break_orbit_sign, rel[0] / dist * self.break_orbit_sign)
        offset = 150.0
        return (
            ship.position[0] + perp[0] * offset,
            ship.position[1] + perp[1] * offset,
        )

    def _path_blocked(
        self, start: Vec2, end: Vec2, obstacles: list, clearance: float = 8.0
    ) -> bool:
        steps = 8
        for i in range(1, steps + 1):
            t = i / steps
            sample = (
                start[0] + (end[0] - start[0]) * t,
                start[1] + (end[1] - start[1]) * t,
            )
            for obs in obstacles:
                if segment_circle_intersect(start, sample, obs.center, obs.collision_radius + clearance):
                    return True
        return False

    def _flank_point(self, ship: Ship, target: Ship, obstacles: list) -> Vec2:
        rel = vec_sub(target.position, ship.position)
        dist = max(vec_len(rel), 1.0)
        perp = (-rel[1] / dist * self.flank_sign, rel[0] / dist * self.flank_sign)
        offset = 160.0
        for _ in range(2):
            candidate = (
                target.position[0] + perp[0] * offset,
                target.position[1] + perp[1] * offset,
            )
            if not self._path_blocked(ship.position, candidate, obstacles):
                return candidate
            self.flank_sign *= -1
            perp = (-perp[1], perp[0])
        return target.position

    def _avoidance_vector(self, ship: Ship, obstacles: list) -> Vec2:
        push = (0.0, 0.0)
        for obs in obstacles:
            dist = vec_len(vec_sub(ship.position, obs.center))
            if dist > ship.radius + obs.collision_radius + 50:
                continue
            away = vec_sub(ship.position, obs.center)
            dist = max(dist, 1.0)
            weight = (ship.radius + obs.collision_radius + 50) / dist
            push = (push[0] + away[0] / dist * weight, push[1] + away[1] / dist * weight)
        return push

    def _angle_diff(self, from_angle: float, to_angle: float) -> float:
        return (to_angle - from_angle + math.pi) % (2 * math.pi) - math.pi

    def _is_stale_tail_chase(self, ship: Ship, target: Ship, angle_diff: float, dist: float) -> bool:
        """Pursuer stuck behind a circling leader."""
        if dist < 55 or dist > 400:
            return False
        if abs(angle_diff) < 0.5:
            return False
        if vec_len(ship.velocity) < 50 or vec_len(target.velocity) < 50:
            return False
        rel = vec_sub(target.position, ship.position)
        to_pursuer = math.atan2(ship.position[1] - target.position[1], ship.position[0] - target.position[0])
        target_heading = (
            math.atan2(target.velocity[1], target.velocity[0])
            if vec_len(target.velocity) > 20
            else target.angle
        )
        tail_align = abs(self._angle_diff(target_heading, to_pursuer))
        return tail_align > 2.0

    def _is_stale_lead_orbit(self, ship: Ship, target: Ship, dist: float) -> bool:
        """Leader being tailed in a stable-distance circle."""
        if dist > 380 or dist < 50:
            return False
        if vec_len(ship.velocity) < 60:
            return False
        rel = vec_sub(target.position, ship.position)
        to_chaser = math.atan2(rel[1], rel[0])
        behind = abs(self._angle_diff(ship.angle, to_chaser))
        return behind > 2.0

    def _radial_speed(self, ship: Ship, toward: Vec2) -> float:
        dist = max(vec_len(toward), 1.0)
        unit = (toward[0] / dist, toward[1] / dist)
        return ship.velocity[0] * unit[0] + ship.velocity[1] * unit[1]

    def _is_mutual_orbit(
        self, ship: Ship, target: Ship, dist: float, dist_delta: float
    ) -> bool:
        """Two ships circling at stable range with little closing speed."""
        if dist < 70 or dist > 340:
            return False
        if dist_delta > 18:
            return False
        if vec_len(ship.velocity) < 55 or vec_len(target.velocity) < 55:
            return False
        rel = vec_sub(target.position, ship.position)
        to_target = math.atan2(rel[1], rel[0])
        to_ship = math.atan2(-rel[1], -rel[0])
        ship_side = abs(self._angle_diff(ship.angle, to_target))
        target_side = abs(self._angle_diff(target.angle, to_ship))
        if ship_side < 0.4 or ship_side > 2.4:
            return False
        if target_side < 0.4 or target_side > 2.4:
            return False
        if abs(self._radial_speed(ship, rel)) > 32:
            return False
        if abs(self._radial_speed(target, (-rel[0], -rel[1]))) > 32:
            return False
        return True

    def _proximity_scale(self, dist: float) -> float:
        """Caution only matters when the threat is actually nearby."""
        if dist >= 360:
            return 0.0
        if dist <= 140:
            return 1.0
        return 1.0 - (dist - 140) / 220

    def _retreat_urgency(
        self, ship: Ship, target: Ship, dist: float, rel: Vec2
    ) -> float:
        """How cautious to be (0 = fight, 1 = panic flee)."""
        health_ratio = ship.health / ship.max_health
        tier_gap = VARIANT_TIER[target.variant] - VARIANT_TIER[ship.variant]
        closing = self._radial_speed(ship, rel)
        proximity = self._proximity_scale(dist)

        health_urgency = 0.0
        if health_ratio < 0.12:
            health_urgency = 0.58
        elif health_ratio < 0.22:
            health_urgency = 0.4
        elif health_ratio < 0.38:
            health_urgency = 0.22

        threat_urgency = 0.0
        if ship.variant == ShipVariant.LIGHT and target.variant == ShipVariant.HEAVY:
            if dist < 240:
                threat_urgency = max(
                    threat_urgency, 0.32 + (240 - dist) / 240 * 0.36
                )
            if dist < 140 and closing > 30:
                threat_urgency = max(threat_urgency, 0.72)
        elif ship.variant == ShipVariant.BALANCED and target.variant == ShipVariant.HEAVY:
            if dist < 95:
                threat_urgency = max(threat_urgency, 0.42)
            elif dist < 155 and health_ratio < 0.28:
                threat_urgency = max(threat_urgency, 0.36)
        elif tier_gap > 0 and dist < 85:
            threat_urgency = max(threat_urgency, 0.34)

        if closing > 70 and dist < 130:
            threat_urgency = max(
                threat_urgency, 0.38 + min(closing, 110) / 200
            )

        urgency = min(1.0, health_urgency * proximity + threat_urgency * proximity)
        if dist > 250:
            urgency *= 0.55
        elif dist > 180:
            urgency *= 0.75
        if self._is_behind_target(ship, target, rel) and health_ratio < 0.52:
            urgency *= 0.18
        elif self._is_behind_target(ship, target, rel):
            urgency *= 0.42
        return urgency

    def _ideal_weapon_range(self, ship: Ship) -> float:
        if ship.variant == ShipVariant.LIGHT:
            return config.AI_IDEAL_RANGE_LIGHT
        if ship.variant == ShipVariant.HEAVY:
            return config.AI_IDEAL_RANGE_HEAVY
        return config.AI_IDEAL_RANGE_BALANCED

    def _in_weapon_sweet_spot(self, ship: Ship, dist: float) -> bool:
        return range_damage_multiplier(ship.variant, dist) >= 1.02

    def _blend_range_thrust(self, ship: Ship, dist: float, base: float) -> float:
        """Nudge thrust toward each hull's preferred damage band."""
        err = dist - self._ideal_weapon_range(ship)
        inner = config.AI_RANGE_INNER_TOLERANCE
        outer = config.AI_RANGE_OUTER_TOLERANCE
        if ship.variant == ShipVariant.LIGHT:
            if err > outer:
                return max(base, 0.82)
            if err > inner * 0.55:
                return max(base, 0.58)
            if err < -inner * 0.45:
                return min(base, 0.38)
            return max(base, 0.42)
        if ship.variant == ShipVariant.HEAVY:
            if err < -inner:
                return min(base, -0.28)
            if err < -inner * 0.45:
                return min(base, 0.12)
            if err > outer * 1.1:
                return max(base, 0.38)
            if err > inner * 0.5:
                return min(base, 0.22)
            return min(base, 0.35)
        if err > outer:
            return max(base, 0.58)
        if err < -outer:
            return min(base, max(0.0, base - 0.18))
        if abs(err) < inner * 0.55:
            return max(base, 0.4)
        return base

    def _kite_point(self, ship: Ship, target: Ship, dist: float, obstacles: list) -> Vec2:
        """Circle at weapon-optimal range instead of reversing forever."""
        rel = vec_sub(target.position, ship.position)
        sep = max(vec_len(rel), 1.0)
        to_target = (rel[0] / sep, rel[1] / sep)
        perp = (-to_target[1] * self.flank_sign, to_target[0] * self.flank_sign)
        ideal = self._ideal_weapon_range(ship)
        inner = config.AI_RANGE_INNER_TOLERANCE
        outer = config.AI_RANGE_OUTER_TOLERANCE
        if dist < ideal - inner:
            blend = -0.5 if ship.variant == ShipVariant.HEAVY else -0.2
        elif dist > ideal + outer:
            blend = 0.45 if ship.variant == ShipVariant.LIGHT else 0.28
        else:
            blend = 0.0
        dir_x = to_target[0] * blend + perp[0] * 0.9
        dir_y = to_target[1] * blend + perp[1] * 0.9
        mag = max(vec_len((dir_x, dir_y)), 0.01)
        scale = 180.0
        candidate = (
            ship.position[0] + dir_x / mag * scale,
            ship.position[1] + dir_y / mag * scale,
        )
        if self._path_blocked(ship.position, candidate, obstacles):
            candidate = (
                ship.position[0] - dir_x / mag * scale,
                ship.position[1] - dir_y / mag * scale,
            )
        return candidate

    def _shield_ram_range(self, ship: Ship) -> float:
        if ship.variant == ShipVariant.HEAVY:
            return 280.0
        if ship.variant == ShipVariant.BALANCED:
            return 240.0
        return 210.0

    def _retreat_point(self, ship: Ship, target: Ship, obstacles: list) -> Vec2:
        rel = vec_sub(ship.position, target.position)
        dist = max(vec_len(rel), 1.0)
        away = (rel[0] / dist, rel[1] / dist)
        perp = (-away[1] * self.flank_sign, away[0] * self.flank_sign)
        candidate = (
            ship.position[0] + away[0] * 220 + perp[0] * 90,
            ship.position[1] + away[1] * 220 + perp[1] * 90,
        )
        if self._path_blocked(ship.position, candidate, obstacles):
            candidate = (
                ship.position[0] + away[0] * 220 - perp[0] * 90,
                ship.position[1] + away[1] * 220 - perp[1] * 90,
            )
        return candidate

    def _injury_speed_control(
        self,
        ship: Ship,
        thrust: float,
        strafe: float,
        threat_dist: float = 999.0,
    ) -> tuple[float, float]:
        """Hurt ships brake instead of maintaining panic speed."""
        ratio = ship.health / ship.max_health
        if ratio >= config.AI_INJURY_HEALTH_RATIO:
            return thrust, strafe
        speed = vec_len(ship.velocity)
        if threat_dist > 320 and speed < 300:
            return min(thrust, 0.42), strafe * 0.8
        if speed > config.AI_INJURY_MAX_SPEED:
            return -0.55, strafe * 0.35
        if speed > config.AI_INJURY_BRAKE_SPEED:
            return min(thrust, -0.3), strafe * 0.5
        if speed > 140:
            return min(thrust, 0.18), strafe * 0.65
        return min(thrust, 0.38), strafe * 0.75

    def _ram_avoid_thrust(self, ship: Ship, others: list[Ship]) -> float | None:
        speed = vec_len(ship.velocity)
        if speed < 120:
            return None
        for other in others:
            if not other.alive or other.ship_id == ship.ship_id:
                continue
            rel = vec_sub(other.position, ship.position)
            dist = vec_len(rel)
            if dist > 130 or dist < 1:
                continue
            closing = self._radial_speed(ship, rel)
            if closing > 60:
                return -0.75
        return None

    def _orbit_break_aim(
        self, ship: Ship, target: Ship, as_pursuer: bool
    ) -> Vec2:
        """Cut across the circle instead of following the tail."""
        rel = vec_sub(target.position, ship.position)
        dist = max(vec_len(rel), 1.0)
        perp = (-rel[1] / dist, rel[0] / dist)
        sign = self.break_orbit_sign * (-1 if as_pursuer else 1)
        offset = 140.0 if as_pursuer else 110.0
        return (
            ship.position[0] + perp[0] * offset * sign,
            ship.position[1] + perp[1] * offset * sign,
        )

    def _assess_combat_situation(
        self,
        ship: Ship,
        target: Ship,
        others: list[Ship],
        dt: float,
        obstacles: list,
        powerups: list,
        arena_rect: tuple[float, float, float, float] | None,
    ) -> CombatSituation:
        """Gather battlefield facts and mode eligibility for this tick."""
        self._update_target_track(target, dt)
        rel_to_target = self._target_delta(ship, target, arena_rect)
        dist = vec_len(rel_to_target)
        opponents = self._living_opponents(ship, others)
        rear_threat = self._nearest_rear_threat(ship, opponents, arena_rect)
        being_tailed = rear_threat is not None
        rear_dist = float("inf")
        if rear_threat is not None:
            rear_rel = self._target_delta(rear_threat, ship, arena_rect)
            rear_dist = vec_len(rear_rel)
        engage_quality = self._engagement_quality(
            ship, target, dist, rel_to_target, obstacles, arena_rect
        )
        behind_target = self._is_behind_target(ship, target, rel_to_target)
        shot_bearing = self._shot_alignment_bearing(ship, target, rel_to_target)
        misaligned_shot = shot_bearing > config.AI_SHOT_ALIGN_BEARING
        closing = self._radial_speed(ship, rel_to_target)
        caution = self._retreat_urgency(ship, target, dist, rel_to_target)
        prof = self.profile
        caution = min(
            1.0,
            caution * (1.35 - 0.35 * prof.risk_tolerance),
        )
        six_close_dist = config.AI_SIX_EVADE_CLOSE_DIST * (
            0.85 + 0.15 * prof.six_evade
        )
        if being_tailed and rear_dist < config.AI_SIX_EVADE_DIST:
            proximity = 1.0 - min(1.0, rear_dist / config.AI_SIX_EVADE_DIST)
            caution = min(
                1.0,
                caution + config.AI_SIX_EVADE_CAUTION * proximity * prof.six_evade,
            )
        has_los = not self._path_blocked(
            ship.position, target.position, obstacles, clearance=12.0
        )
        to_target = math.atan2(rel_to_target[1], rel_to_target[0])
        target_bearing = abs(self._angle_diff(ship.angle, to_target))
        shield_ramming = (
            ship.shield_timer > 0 and dist < self._shield_ram_range(ship)
        )

        panic_pull = caution >= 0.78 and not shield_ramming
        panicking = panic_pull and dist < 210

        pickup = self._best_powerup_target(
            ship, powerups, dist, caution, obstacles, others, arena_rect
        )
        seeking_powerup = False
        pickup_bias = 0.0
        pickup_field_risk = 0.0
        if pickup and not shield_ramming:
            pu, pu_dist, pu_score = pickup
            pickup_field_risk = self._powerup_field_risk(
                ship, pu, others, arena_rect
            )
            hurt = ship.health < ship.max_health * 0.55
            shield_grab = (
                pu.kind == PowerUpKind.SHIELD
                and pu_dist < 170
                and hurt
                and pu_score >= config.AI_POWERUP_EASY_REACH_SCORE
            )
            seek_score = config.AI_POWERUP_SEEK_SCORE / prof.powerup_greed
            easy_score = config.AI_POWERUP_EASY_REACH_SCORE / prof.powerup_greed
            easy_reach = (
                pu_dist < config.AI_POWERUP_EASY_REACH_DIST
                and pu_score >= easy_score
                and not self._path_blocked(
                    ship.position, pu.position, obstacles, clearance=10
                )
            )
            commit_pickup = (
                pu_score >= seek_score
                or easy_reach
                or shield_grab
            )
            if pickup_field_risk >= config.AI_POWERUP_ABORT_RISK:
                commit_pickup = bool(shield_grab)
            elif pickup_field_risk >= config.AI_POWERUP_CAUTION_RISK:
                commit_pickup = bool(shield_grab) or (
                    easy_reach and pu_score >= 0.42
                )
            if commit_pickup:
                seeking_powerup = True
            elif pu_score >= 0.28 and not panicking:
                pickup_bias = min(0.48, pu_score - 0.08)

        tail_dist_min = config.AI_TAIL_MAINTAIN_DIST_MIN / prof.tail_hold
        tail_dist_max = config.AI_TAIL_MAINTAIN_DIST_MAX * (
            0.92 + 0.08 * prof.tail_hold
        )
        tail_hold_bearing = config.AI_TAIL_HOLD_BEARING * (
            1.0 + 0.25 * (prof.tail_hold - 1.0)
        )
        tail_hold_engage = config.AI_TAIL_HOLD_ENGAGE / prof.tail_hold
        tail_gunner = (
            behind_target
            and not seeking_powerup
            and not shield_ramming
            and tail_dist_min < dist < tail_dist_max
            and (
                misaligned_shot
                or ship.health < ship.max_health * 0.52
                or shot_bearing < tail_hold_bearing
                or engage_quality >= tail_hold_engage
            )
            and not (
                ship.health < ship.max_health * 0.28
                and VARIANT_TIER[target.variant] > VARIANT_TIER[ship.variant]
            )
        )
        six_evade = (
            being_tailed
            and rear_threat is not None
            and rear_dist < six_close_dist
            and not tail_gunner
            and not shield_ramming
            and not seeking_powerup
        )
        if tail_gunner:
            panicking = False
            panic_pull = False
        if six_evade:
            panicking = False

        reverse_eligible = (
            self._reverse_gun_eligible(
                ship,
                target,
                dist,
                rel_to_target,
                closing,
                behind_target,
                has_los,
            )
            and not shield_ramming
            and not seeking_powerup
            and not tail_gunner
            and not six_evade
        )
        reverse_gun = False
        if self.reverse_gun_cooldown > 0:
            self.reverse_gun_cooldown = max(0.0, self.reverse_gun_cooldown - dt)
        if self.reverse_gun_commit_timer > 0:
            lost_aim = target_bearing > 1.05
            if dist > config.AI_REVERSE_GUN_ABORT_DIST or lost_aim or not has_los:
                self.reverse_gun_commit_timer = 0.0
                self.reverse_gun_cooldown = config.AI_REVERSE_GUN_COOLDOWN * 0.5
            else:
                reverse_gun = True
                self.reverse_gun_commit_timer = max(
                    0.0, self.reverse_gun_commit_timer - dt
                )
                if self.reverse_gun_commit_timer <= 0:
                    self.reverse_gun_cooldown = config.AI_REVERSE_GUN_COOLDOWN
        elif reverse_eligible:
            self.reverse_gun_eligible_timer += dt
            reverse_eligible_after = (
                config.AI_REVERSE_GUN_ELIGIBLE_AFTER / prof.reverse_gun
            )
            if (
                self.reverse_gun_eligible_timer >= reverse_eligible_after
                and self.reverse_gun_cooldown <= 0
            ):
                reverse_gun = True
                self.reverse_gun_commit_timer = config.AI_REVERSE_GUN_COMMIT
                self.reverse_gun_eligible_timer = 0.0
        else:
            self.reverse_gun_eligible_timer = max(
                0.0, self.reverse_gun_eligible_timer - dt * 0.6
            )

        if reverse_gun:
            panicking = False
        kite_caution_min = 0.28 / max(0.55, prof.kite_retreat)
        kiting = (
            (caution >= kite_caution_min or (panic_pull and dist >= 210))
            and not panicking
            and not shield_ramming
            and not tail_gunner
            and not six_evade
            and not reverse_gun
            and not seeking_powerup
        )

        self.kite_burst_timer -= dt
        self.panic_burst_timer -= dt
        snap_shot = kiting and self.kite_burst_timer > 0
        if kiting and self.kite_burst_timer <= 0 and random.random() < 0.022:
            self.kite_burst_timer = random.uniform(0.45, 0.8)
        panic_snap = panicking and self.panic_burst_timer > 0
        if panicking and self.panic_burst_timer <= 0 and random.random() < 0.04:
            self.panic_burst_timer = random.uniform(0.35, 0.7)
        reengage = (
            ship.health < ship.max_health * 0.42
            and dist > 300
            and caution < 0.2
        )
        heavy_duel = (
            self._is_heavy_duel(ship, target, opponents)
            and ship.health >= ship.max_health * 0.35
            and not panicking
            and not shield_ramming
            and not seeking_powerup
            and not tail_gunner
            and not six_evade
            and not reverse_gun
        )
        if heavy_duel:
            if abs(dist - self.last_dist) < 14.0 and abs(closing) < 35.0:
                self.heavy_duel_stale_timer += dt
            else:
                self.heavy_duel_stale_timer = max(
                    0.0, self.heavy_duel_stale_timer - dt * 0.6
                )
            heavy_commit_after = (
                config.AI_HEAVY_DUEL_COMMIT_AFTER / prof.heavy_commit
            )
            if self.heavy_duel_stale_timer >= heavy_commit_after:
                self.heavy_duel_commit_timer = config.AI_HEAVY_DUEL_COMMIT_DURATION
                self.heavy_duel_stale_timer = 0.0
        else:
            self.heavy_duel_stale_timer = max(0.0, self.heavy_duel_stale_timer - dt)
        self.heavy_duel_commit_timer = max(0.0, self.heavy_duel_commit_timer - dt)

        solo_dogfight = (
            len(opponents) == 1
            and ship.health >= ship.max_health * 0.35
            and 55 < dist < config.AI_SOLO_DOGFIGHT_MAX_DIST
            and not panicking
            and not shield_ramming
            and not seeking_powerup
            and not tail_gunner
            and not six_evade
            and not reverse_gun
            and not heavy_duel
        )
        center_bias_scale = (
            config.AI_HEAVY_DUEL_CENTER_BIAS if heavy_duel else 1.0
        )
        return CombatSituation(
            ship=ship,
            target=target,
            opponents=opponents,
            obstacles=obstacles,
            powerups=powerups,
            arena_rect=arena_rect,
            rel_to_target=rel_to_target,
            dist=dist,
            closing=closing,
            has_los=has_los,
            engage_quality=engage_quality,
            behind_target=behind_target,
            shot_bearing=shot_bearing,
            misaligned_shot=misaligned_shot,
            target_bearing=target_bearing,
            rear_threat=rear_threat,
            being_tailed=being_tailed,
            rear_dist=rear_dist,
            caution=caution,
            shield_ramming=shield_ramming,
            panic_pull=panic_pull,
            panicking=panicking,
            panic_snap=panic_snap,
            pickup=pickup,
            seeking_powerup=seeking_powerup,
            pickup_bias=pickup_bias,
            pickup_field_risk=pickup_field_risk,
            tail_gunner=tail_gunner,
            six_evade=six_evade,
            reverse_gun=reverse_gun,
            reverse_eligible=reverse_eligible,
            kiting=kiting,
            snap_shot=snap_shot,
            reengage=reengage,
            heavy_duel=heavy_duel,
            solo_dogfight=solo_dogfight,
            center_bias_scale=center_bias_scale,
        )

    def update(
        self,
        ship: Ship,
        others: list[Ship],
        dt: float,
        obstacles: list | None = None,
        powerups: list | None = None,
        arena_rect: tuple[float, float, float, float] | None = None,
    ) -> tuple[float, float, bool]:
        """Return rotate_dir (-1/0/1), thrust_dir, should_fire."""
        obs = obstacles or []
        pickups = powerups or []
        target = self._select_combat_target(ship, others, obs, arena_rect)
        if target is None:
            self.wander_timer -= dt
            self.last_situation = None
            if self.wander_timer <= 0:
                self.wander_timer = random.uniform(0.5, 1.5)
            rot = float(random.choice([-1, 0, 1]))
            self.last_context = AIDecisionContext(mode="wander", rotate=rot)
            return (rot, 0.0, False)

        sit = self._assess_combat_situation(
            ship, target, others, dt, obs, pickups, arena_rect
        )
        self.last_situation = sit
        prof = self.profile
        rel_to_target = sit.rel_to_target
        dist = sit.dist
        opponents = sit.opponents
        rear_threat = sit.rear_threat
        being_tailed = sit.being_tailed
        rear_dist = sit.rear_dist
        engage_quality = sit.engage_quality
        behind_target = sit.behind_target
        shot_bearing = sit.shot_bearing
        misaligned_shot = sit.misaligned_shot
        closing = sit.closing
        caution = sit.caution
        has_los = sit.has_los
        shield_ramming = sit.shield_ramming
        panic_pull = sit.panic_pull
        panicking = sit.panicking
        panic_snap = sit.panic_snap
        pickup = sit.pickup
        seeking_powerup = sit.seeking_powerup
        pickup_bias = sit.pickup_bias
        pickup_field_risk = sit.pickup_field_risk
        tail_gunner = sit.tail_gunner
        six_evade = sit.six_evade
        reverse_gun = sit.reverse_gun
        kiting = sit.kiting
        snap_shot = sit.snap_shot
        reengage = sit.reengage
        heavy_duel = sit.heavy_duel
        solo_dogfight = sit.solo_dogfight
        center_bias_scale = sit.center_bias_scale
        target_bearing = sit.target_bearing
        to_target = math.atan2(rel_to_target[1], rel_to_target[0])

        if shield_ramming:
            aim_pos = (
                vec_add(ship.position, rel_to_target)
                if dist < 130
                else self.lead_target(ship, target, arena_rect)
            )
        elif six_evade and rear_threat is not None:
            aim_pos = self._break_six_aim(ship, rear_threat, arena_rect)
        elif reverse_gun:
            aim_pos = self.lead_target(ship, target, arena_rect)
        elif tail_gunner:
            aim_pos = self._aim_when_behind(
                ship, target, rel_to_target, arena_rect, misaligned_shot
            )
        elif seeking_powerup and pickup:
            aim_pos = pickup[0].position
        elif reengage or (kiting and dist > 320):
            aim_pos = self.lead_target(ship, target, arena_rect)
        elif panicking:
            if behind_target or panic_snap:
                aim_pos = self.lead_target(ship, target, arena_rect)
            elif dist > 115:
                aim_pos = self._kite_point(ship, target, dist, obs)
            else:
                aim_pos = self._retreat_point(ship, target, obs)
        elif snap_shot:
            aim_pos = self.lead_target(ship, target, arena_rect)
        elif kiting:
            aim_pos = self._kite_point(ship, target, dist, obs)
        elif heavy_duel and self.heavy_duel_commit_timer > 0:
            aim_pos = self._predict_target_position(target, 0.32, ship.variant)
        else:
            aim_pos = self.lead_target(ship, target, arena_rect)
        if pickup_bias > 0 and pickup and not seeking_powerup:
            pu_pos = pickup[0].position
            aim_pos = (
                aim_pos[0] * (1.0 - pickup_bias) + pu_pos[0] * pickup_bias,
                aim_pos[1] * (1.0 - pickup_bias) + pu_pos[1] * pickup_bias,
            )
        blocked = self._path_blocked(ship.position, aim_pos, obs)
        if (
            blocked
            and not panicking
            and not kiting
            and not reverse_gun
            and not shield_ramming
            and not seeking_powerup
        ):
            aim_pos = self._flank_point(ship, target, obs)

        avoid = self._avoidance_vector(ship, obs)
        if vec_len(avoid) > 0.2 and not shield_ramming:
            scale = 110 if panicking else 90
            aim_pos = (
                aim_pos[0] + avoid[0] * scale,
                aim_pos[1] + avoid[1] * scale,
            )

        aim_pos = self._bias_aim_toward_center(
            ship, aim_pos, arena_rect, center_bias_scale
        )
        angle_diff, rotate_dir, _ = self._steer_from_aim(ship, aim_pos)
        turn_gate = 0.08 if shield_ramming else 0.15
        if abs(angle_diff) <= turn_gate:
            rotate_dir = 0.0

        thrust = 0.0
        strafe = 0.0
        breaking_orbit = False
        orbit_force_shot = False

        fire_cone = 0.7
        fire_range = 750.0
        if ship.variant == ShipVariant.LIGHT:
            fire_cone = 0.82
            fire_range = 820.0
        stale_tail = self._is_stale_tail_chase(ship, target, angle_diff, dist)
        stale_lead = self._is_stale_lead_orbit(ship, target, dist)
        stale_mutual = self._is_mutual_orbit(ship, target, dist, abs(dist - self.last_dist))
        dist_delta = abs(dist - self.last_dist)
        self.last_dist = dist

        if stale_tail and dist_delta < 25:
            self.chase_stale_timer += dt
        else:
            self.chase_stale_timer = max(0.0, self.chase_stale_timer - dt * 0.5)

        if stale_lead and dist_delta < 30:
            self.lead_stale_timer += dt
        else:
            self.lead_stale_timer = max(0.0, self.lead_stale_timer - dt * 0.5)

        if stale_mutual and dist_delta < 20:
            self.orbit_stale_timer += dt
        else:
            self.orbit_stale_timer = max(0.0, self.orbit_stale_timer - dt * 0.8)

        break_chase = self.chase_stale_timer > config.ORBIT_BREAK_CHASE_TIMER
        break_lead = self.lead_stale_timer > config.ORBIT_BREAK_LEAD_TIMER
        break_mutual = self.orbit_stale_timer > config.ORBIT_BREAK_MUTUAL_TIMER
        if (
            (break_chase or break_lead or break_mutual)
            and not panicking
            and not shield_ramming
            and not seeking_powerup
            and not tail_gunner
            and not six_evade
            and not reverse_gun
            and not behind_target
        ):
            breaking_orbit = True
            self.orbit_break_timer += dt
            force_start = config.ORBIT_BREAK_FORCE_SHOT_TIMER
            force_end = force_start + config.ORBIT_BREAK_FORCE_SHOT_WINDOW
            orbit_force_shot = force_start <= self.orbit_break_timer < force_end
            as_pursuer = break_chase and self.chase_stale_timer >= self.lead_stale_timer
            shoot_first = has_los and dist < fire_range
            if orbit_force_shot or shoot_first:
                aim_pos = self.lead_target(ship, target, arena_rect)
            else:
                aim_pos = self._orbit_break_aim(ship, target, as_pursuer=as_pursuer)
            dx = aim_pos[0] - ship.position[0]
            dy = aim_pos[1] - ship.position[1]
            desired = math.atan2(dy, dx)
            angle_diff = self._angle_diff(ship.angle, desired)
            gate = config.ORBIT_BREAK_AIM_GATE
            rotate_dir = 1.0 if angle_diff > gate else (-1.0 if angle_diff < -gate else 0.0)
            if orbit_force_shot:
                thrust = 0.78 if dist > fire_range else 0.24
                strafe = self.flank_sign * 0.08
            elif shoot_first:
                thrust = 0.32 if dist > 140 else 0.16
                strafe = self.flank_sign * 0.22
            elif break_mutual and not break_chase and not break_lead:
                thrust = -0.5 if ship.ship_id % 2 == 0 else 1.0
                strafe = self.break_orbit_sign * 1.6
            else:
                thrust = 0.25 if as_pursuer else -0.35
                strafe = self.break_orbit_sign * 1.4
            if (
                self.chase_stale_timer > config.ORBIT_BREAK_MAX_DURATION + 0.7
                or self.lead_stale_timer > config.ORBIT_BREAK_MAX_DURATION + 0.8
                or self.orbit_stale_timer > config.ORBIT_BREAK_MAX_DURATION
                or self.orbit_break_timer >= force_end
            ):
                self.chase_stale_timer = 0.0
                self.lead_stale_timer = 0.0
                self.orbit_stale_timer = 0.0
                self.orbit_break_timer = 0.0
                self.break_orbit_sign *= -1
        else:
            self.orbit_break_timer = max(0.0, self.orbit_break_timer - dt * 2.0)

        self.jitter_timer -= dt
        orbit_shoot_first = breaking_orbit and (
            orbit_force_shot or (has_los and dist < fire_range)
        )
        if breaking_orbit and not orbit_shoot_first and self.jitter_timer <= 0:
            jitter = vec_from_angle(
                ship.angle + self.break_orbit_sign * 1.57,
                random.uniform(40, 90),
            )
            aim_pos = (aim_pos[0] + jitter[0], aim_pos[1] + jitter[1])
            self.jitter_timer = random.uniform(0.25, 0.55)

        aim_pos = self._bias_aim_toward_center(
            ship, aim_pos, arena_rect, center_bias_scale
        )
        angle_diff, rotate_dir, _ = self._steer_from_aim(ship, aim_pos)
        turn_gate = 0.08 if shield_ramming else 0.15
        if abs(angle_diff) <= turn_gate:
            rotate_dir = 0.0

        if shield_ramming:
            thrust = 1.0
            if abs(angle_diff) > 0.55:
                strafe = self.flank_sign * 0.7
        elif seeking_powerup and pickup:
            pu_dist = pickup[1]
            if pickup_field_risk >= config.AI_POWERUP_CAUTION_RISK:
                thrust = 0.24 if pu_dist > 70 else 0.14
            elif pu_dist > 120:
                thrust = 0.52
            elif pu_dist > 55:
                thrust = 0.34
            else:
                thrust = 0.18
            strafe = self.flank_sign * (0.22 if pickup_field_risk >= config.AI_POWERUP_CAUTION_RISK else 0.32)
        elif pickup_bias > 0:
            thrust = 0.62
            strafe = self.flank_sign * 0.35
        elif (
            ship.variant == ShipVariant.LIGHT
            and target.variant == ShipVariant.HEAVY
            and ship.health < ship.max_health * 0.42
            and dist < 175
        ):
            thrust = -0.52
            strafe = self.flank_sign * 0.95
        elif six_evade:
            thrust = config.AI_SIX_BREAK_THRUST
            strafe = self.break_orbit_sign * config.AI_SIX_BREAK_STRAFE
        elif reverse_gun:
            thrust = self._reverse_gun_thrust(ship, self.reverse_gun_commit_timer)
            strafe = self.flank_sign * 0.08
        elif tail_gunner:
            ideal = self._ideal_weapon_range(ship)
            inner = config.AI_RANGE_INNER_TOLERANCE
            outer = config.AI_RANGE_OUTER_TOLERANCE
            if dist > ideal + outer:
                thrust = 0.58 if misaligned_shot else 0.44
            elif dist < ideal - inner * 0.65:
                thrust = -0.1 if closing > 35 else 0.12
            else:
                thrust = 0.38 if misaligned_shot else 0.3
            if vec_len(target.velocity) > 45 and not misaligned_shot:
                thrust = max(thrust, 0.28)
            if misaligned_shot and abs(angle_diff) > 0.35:
                strafe = rotate_dir * 0.22
            else:
                strafe = self.flank_sign * 0.1
        elif reengage or (kiting and dist > 320):
            thrust = 0.7 if dist > 400 else 0.5
            strafe = self.flank_sign * 0.6
        elif panicking:
            hurt_panic = ship.health < ship.max_health * config.AI_INJURY_HEALTH_RATIO
            if dist > 115:
                thrust = 0.22 if hurt_panic else (0.4 if closing > 40 else 0.32)
                strafe = self.flank_sign * (0.45 if hurt_panic else 0.95)
            else:
                thrust = 0.18 if hurt_panic else (0.48 if closing > 35 else 0.28)
                strafe = self.flank_sign * (0.4 if hurt_panic else (0.75 + caution * 0.35))
        elif kiting:
            ideal = self._ideal_weapon_range(ship)
            if snap_shot:
                thrust = 0.25
            elif dist > ideal + config.AI_RANGE_OUTER_TOLERANCE:
                thrust = 0.62 if ship.variant == ShipVariant.LIGHT else 0.48
            elif dist < ideal - config.AI_RANGE_INNER_TOLERANCE and closing > 25:
                thrust = -0.18 if ship.variant == ShipVariant.HEAVY else -0.08
            else:
                thrust = 0.38
            thrust = self._blend_range_thrust(ship, dist, thrust)
            strafe = self.flank_sign * 1.0
        elif heavy_duel and not breaking_orbit:
            ideal = self._ideal_weapon_range(ship)
            inner = config.AI_RANGE_INNER_TOLERANCE
            outer = config.AI_RANGE_OUTER_TOLERANCE
            if dist < 235 and closing > 38:
                thrust = -0.48
                strafe = self.break_orbit_sign * 0.95
            elif dist < 320 and closing < -52:
                thrust = config.AI_HEAVY_DUEL_COMMIT_THRUST
                strafe = self.flank_sign * 0.1
            elif self.heavy_duel_commit_timer > 0 and dist > 260:
                thrust = config.AI_HEAVY_DUEL_COMMIT_THRUST
                strafe = self.flank_sign * 0.08
            elif dist > ideal + outer:
                thrust = 0.88
                strafe = self.flank_sign * 0.1
            elif dist > ideal + inner * 0.55:
                thrust = config.AI_HEAVY_DUEL_CLOSE_THRUST
                strafe = self.flank_sign * 0.14
            elif dist < ideal - inner:
                thrust = -0.22
                strafe = self.flank_sign * 0.42
            else:
                thrust = config.AI_HEAVY_DUEL_BAND_THRUST
                strafe = self.flank_sign * 0.36
            if closing < -18.0:
                thrust = max(thrust, config.AI_HEAVY_DUEL_COMMIT_THRUST)
                strafe *= 0.22
        elif not breaking_orbit:
            health_ratio = ship.health / ship.max_health
            if self.personality == Personality.AGGRESSIVE:
                if ship.variant == ShipVariant.LIGHT and target.variant == ShipVariant.HEAVY:
                    if health_ratio < 0.38 and dist < 160:
                        thrust = -0.55
                        strafe = self.flank_sign * 1.1
                    elif dist > self._ideal_weapon_range(ship) + 80:
                        thrust = 0.88
                    elif dist < 110:
                        thrust = 0.38
                    else:
                        thrust = 0.55
                elif ship.variant == ShipVariant.HEAVY and target.variant == ShipVariant.LIGHT:
                    if dist < self._ideal_weapon_range(ship) - 120:
                        thrust = -0.32 if closing > 25 else -0.18
                    elif dist > self._ideal_weapon_range(ship) + 60:
                        thrust = 0.22
                    else:
                        thrust = 0.3
                elif ship.variant == ShipVariant.LIGHT and dist < 70:
                    thrust = 0.42
                else:
                    thrust = 0.68 if dist > 80 else 0.38
                    if blocked:
                        thrust = 0.62
            elif self.personality == Personality.DEFENSIVE:
                if ship.health < ship.max_health * 0.4 and not tail_gunner:
                    retreat = -0.6 * (1.45 - 0.45 * prof.risk_tolerance)
                    thrust = max(-0.92, retreat)
                    strafe = 1.0 if random.random() > 0.5 else -1.0
                else:
                    thrust = 0.7 if blocked else 0.5
            else:
                thrust = 0.85
                strafe = 1.0 if angle_diff > 0 else -1.0
            thrust = max(-0.95, min(1.0, thrust * prof.chase_push))
            strafe *= prof.flank_strafe
            if not tail_gunner and not shield_ramming:
                thrust = self._blend_range_thrust(ship, dist, thrust)
            if solo_dogfight and not breaking_orbit:
                strafe = self.flank_sign * 0.82
                ideal = self._ideal_weapon_range(ship)
                in_band = abs(dist - ideal) < config.AI_RANGE_OUTER_TOLERANCE
                if (
                    engage_quality >= config.AI_ENGAGE_QUALITY_THRESHOLD
                    and (self._in_weapon_sweet_spot(ship, dist) or in_band)
                ):
                    cap = (
                        config.AI_ENGAGE_SNAP_THRUST
                        if engage_quality >= 0.74
                        else config.AI_ENGAGE_HOLD_THRUST
                    )
                    thrust = min(thrust, cap)

        facing_target = target_bearing < 0.42

        should_fire = has_los and facing_target and dist < fire_range
        if tail_gunner:
            cone = 0.82 if misaligned_shot else 0.68
            should_fire = (
                has_los
                and dist < fire_range
                and abs(self._angle_diff(ship.angle, to_target)) < cone
            )
        elif six_evade and rear_threat is not None:
            rear_rel = self._target_delta(ship, rear_threat, arena_rect)
            to_rear = math.atan2(rear_rel[1], rear_rel[0])
            rear_los = not self._path_blocked(
                ship.position, rear_threat.position, obs, clearance=12.0
            )
            should_fire = (
                rear_los
                and rear_dist < fire_range
                and abs(self._angle_diff(ship.angle, to_rear)) < 0.85
            )
        elif reverse_gun:
            should_fire = (
                has_los
                and dist < fire_range
                and target_bearing < 0.62
            )
        elif shield_ramming:
            should_fire = (
                has_los
                and dist > 75
                and dist < fire_range
                and abs(self._angle_diff(ship.angle, to_target)) < 0.5
            )
        elif panicking:
            if behind_target or panic_snap or dist > 115:
                should_fire = (
                    has_los
                    and dist < fire_range
                    and abs(self._angle_diff(ship.angle, to_target)) < 0.68
                )
            else:
                should_fire = (
                    has_los
                    and dist < fire_range * 0.85
                    and abs(self._angle_diff(ship.angle, to_target)) < 0.5
                )
        elif kiting:
            cone = 0.58
            if self._in_weapon_sweet_spot(ship, dist):
                cone = 0.72
            should_fire = should_fire and abs(self._angle_diff(ship.angle, to_target)) < cone
        elif heavy_duel:
            cone = 0.92 if dist > 360 else 0.78
            should_fire = (
                has_los
                and dist < fire_range
                and (
                    abs(self._angle_diff(ship.angle, to_target)) < cone
                    or (
                        self._in_weapon_sweet_spot(ship, dist)
                        and target_bearing < 1.05
                    )
                )
            )
        elif breaking_orbit:
            in_force_range = has_los and dist < config.ORBIT_BREAK_FORCE_FIRE_RANGE
            if orbit_force_shot:
                should_fire = in_force_range
            elif has_los and dist < fire_range:
                should_fire = (
                    target_bearing < config.ORBIT_BREAK_FIRE_BEARING
                    or abs(angle_diff) < 0.78
                    or abs(self._angle_diff(ship.angle, to_target)) < 0.72
                )
            else:
                should_fire = False
        else:
            cone = fire_cone
            if self._in_weapon_sweet_spot(ship, dist):
                cone = min(0.95, fire_cone + 0.18)
            if solo_dogfight and engage_quality >= config.AI_ENGAGE_QUALITY_THRESHOLD:
                cone = min(0.98, cone + 0.14)
            should_fire = should_fire and abs(angle_diff) < cone

        speed = vec_len(ship.velocity)
        if thrust > 0.3 and speed < 25:
            self.stuck_timer += dt
        else:
            self.stuck_timer = max(0.0, self.stuck_timer - dt * 2)

        if (
            self.stuck_timer > 0.8
            and not shield_ramming
            and not tail_gunner
            and not six_evade
            and not reverse_gun
            and not heavy_duel
        ):
            thrust = -0.8
            strafe = self.flank_sign
            rotate_dir = -rotate_dir if rotate_dir != 0 else self.flank_sign
            if self.stuck_timer > 1.6:
                self.stuck_timer = 0.0
                self.flank_sign *= -1

        if vec_len(avoid) > 0.8 and speed < 40 and not shield_ramming:
            avoid_dir = math.atan2(avoid[1], avoid[0])
            slide = self._angle_diff(ship.angle, avoid_dir)
            if abs(slide) > 0.3:
                strafe = 1.0 if slide > 0 else -1.0
            thrust = max(thrust, 0.6)

        hurt_ship = ship.health < ship.max_health * config.AI_INJURY_HEALTH_RATIO
        if not shield_ramming:
            if not reverse_gun:
                ram_brake = self._ram_avoid_thrust(ship, others)
                if ram_brake is not None:
                    thrust = ram_brake
                    strafe *= 0.4
            if not reverse_gun:
                thrust, strafe = self._injury_speed_control(
                    ship, thrust, strafe, dist
                )
        if (
            thrust < 0
            and (dist > 220 or -closing > 50)
            and not hurt_ship
            and not reverse_gun
        ):
            thrust = 0.2 if dist > 300 else 0.0

        if strafe != 0:
            ship.apply_thrust(strafe * 1.57, dt)

        will_fire = should_fire and ship.can_fire()
        if tail_gunner:
            mode = "tail_gunner"
        elif six_evade:
            mode = "six_evade"
        elif reverse_gun:
            mode = "reverse_gun"
        elif shield_ramming:
            mode = "shield_ram"
        elif seeking_powerup:
            mode = "powerup"
        elif panicking:
            mode = "panic"
        elif kiting:
            mode = "kite"
        elif breaking_orbit:
            mode = "orbit_break"
        elif heavy_duel:
            mode = "heavy_duel"
        else:
            mode = "fight"
        self.last_context = AIDecisionContext(
            mode=mode,
            archetype=self.profile.archetype.value,
            target_id=target.ship_id,
            target_dist=dist,
            caution=caution,
            behind_target=behind_target,
            tail_gunner=tail_gunner,
            being_tailed=being_tailed,
            six_evade=six_evade,
            reverse_gun=reverse_gun,
            panicking=panicking,
            kiting=kiting,
            shield_ramming=shield_ramming,
            seeking_powerup=seeking_powerup,
            breaking_orbit=breaking_orbit,
            heavy_duel=heavy_duel,
            engage_quality=engage_quality,
            rotate=rotate_dir,
            thrust=thrust,
            fired=will_fire,
        )
        return rotate_dir, thrust, will_fire