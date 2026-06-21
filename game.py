"""Core game simulation (headless-testable)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

import config
from ai import AIController
from arena import Arena
from combat import (
    PowerUp,
    fire_weapon,
    maybe_spawn_powerup,
    powerup_collected,
    powerup_sound_name,
    projectile_hit_damage,
    projectile_hits_ship,
    random_powerup_kind,
    resolve_ship_collision,
    ships_collide,
    spawn_powerup_at,
)
from particle import ParticleSystem
from ship import Ship, ShipVariant, pick_enemy_color
from utils import vec_len, vec_sub, wrap_position


class GameMode(str, Enum):
    HUMAN = "human"
    AI_ARENA = "ai_arena"


class Phase(str, Enum):
    MENU = "menu"
    WAVE_BREAK = "wave_break"
    PLAYING = "playing"
    GAME_OVER = "game_over"
    AI_PAUSE = "ai_pause"


@dataclass
class GameState:
    mode: GameMode = GameMode.HUMAN
    phase: Phase = Phase.MENU
    arena: Arena | None = None
    player: Ship | None = None
    player_variant: ShipVariant = ShipVariant.BALANCED
    enemies: list[Ship] = field(default_factory=list)
    all_ships: list[Ship] = field(default_factory=list)
    projectiles: list = field(default_factory=list)
    powerups: list[PowerUp] = field(default_factory=list)
    particles: ParticleSystem = field(default_factory=ParticleSystem)
    ai_controllers: dict[int, AIController] = field(default_factory=dict)
    wave: int = 1
    score: int = 0
    survival_time: float = 0.0
    enemy_spawn_timer: float = 0.0
    ai_restart_timer: float = 0.0
    ai_bout_number: int = 0
    ai_prev_living_count: int = 0
    ai_pending_boss_bout: bool = False
    ai_boss_bout_active: bool = False
    ai_boss_bout_cooldown: int = 0
    powerup_spawn_timer: float = 0.0
    screen_flash: float = 0.0
    next_ship_id: int = 1
    kills: int = 0
    pending_sounds: list[str] = field(default_factory=list)

    def start_human(self, variant: ShipVariant) -> None:
        self.mode = GameMode.HUMAN
        self.phase = Phase.PLAYING
        self.player_variant = variant
        self.wave = 1
        self.score = 0
        self.kills = 0
        self.survival_time = 0.0
        self.enemy_spawn_timer = 0.0
        self.projectiles.clear()
        self.powerups.clear()
        self.particles = ParticleSystem()
        self.enemies = []
        if self.arena:
            self.player = Ship.create(
                self.player_variant,
                self.arena.player_spawn_point(),
                is_player=True,
                ship_id=self._next_id(),
            )
            self.player.spawn_invuln = config.SPAWN_INVULN_SECONDS
            self._spawn_wave_enemies()
            self.arena.init_asteroid_field()
        else:
            self.player = None

    def start_wave(self) -> None:
        """Spawn enemies for the current wave; player keeps flying."""
        if self.arena is None:
            return
        if self.player is None or not self.player.alive:
            spawn = self.arena.player_spawn_point()
            self.player = Ship.create(
                self.player_variant,
                spawn,
                is_player=True,
                ship_id=self._next_id(),
            )
            self.player.ai_controlled = False
        self._spawn_wave_enemies()
        self.phase = Phase.PLAYING
        self.enemy_spawn_timer = 0.0

    def _spawn_wave_enemies(self) -> None:
        if self.arena is None:
            return
        saved_pos = self.player.position if self.player else None
        saved_vel = self.player.velocity if self.player else None
        saved_angle = self.player.angle if self.player else None
        avoid = saved_pos if saved_pos else self.arena.player_spawn_point()
        self.enemies, self.next_ship_id = self.arena.spawn_enemies(
            self.wave, self.next_ship_id, avoid=avoid
        )
        self._rebuild_controllers()
        if self.player and saved_pos is not None:
            self.player.position = saved_pos
            self.player.velocity = saved_vel or (0.0, 0.0)
            if saved_angle is not None:
                self.player.angle = saved_angle

    def start_ai_arena(self) -> None:
        self.mode = GameMode.AI_ARENA
        self.phase = Phase.PLAYING
        self.wave = 0
        self.ai_bout_number = 1
        self.ai_prev_living_count = 0
        self.ai_pending_boss_bout = False
        self.ai_boss_bout_active = False
        self.ai_boss_bout_cooldown = 0
        self.score = 0
        self.kills = 0
        self.projectiles.clear()
        self.powerups.clear()
        self.particles = ParticleSystem()
        self.all_ships = []
        self.ai_controllers.clear()
        if self.arena is None:
            return
        self.arena.init_asteroid_field()
        self._spawn_bout_powerups()
        self.powerup_spawn_timer = config.POWERUP_AI_SPAWN_INTERVAL
        variants = list(ShipVariant)
        for _ in range(config.AI_ARENA_SHIP_COUNT):
            variant = random.choice(variants)
            ship = Ship.create(
                variant,
                self.arena.spawn_point_inner(),
                ship_id=self._next_id(),
                enemy_color=pick_enemy_color(),
            )
            ship.ai_controlled = True
            self.all_ships.append(ship)
            self.ai_controllers[ship.ship_id] = AIController.for_ship(ship)
        self.player = None
        self.enemies = self.all_ships

    def _next_id(self) -> int:
        sid = self.next_ship_id
        self.next_ship_id += 1
        return sid

    def _rebuild_controllers(self) -> None:
        self.ai_controllers.clear()
        for ship in self.enemies:
            self.ai_controllers[ship.ship_id] = AIController.for_ship(ship)
        self.all_ships = ([self.player] if self.player else []) + self.enemies

    def living_ships(self) -> list[Ship]:
        if self.mode == GameMode.AI_ARENA:
            return [s for s in self.all_ships if s.alive]
        ships = [s for s in ([self.player] if self.player else []) + self.enemies if s.alive]
        return ships

    def update(self, dt: float, actions: dict) -> None:
        if self.phase == Phase.MENU:
            return
        if self.phase == Phase.GAME_OVER:
            return
        if self.arena is None:
            return

        self.pending_sounds.clear()
        rect = self.arena.rect
        self.arena.update_asteroids(dt)
        self.survival_time += dt
        if self.mode == GameMode.HUMAN:
            self.score += int(config.SCORE_PER_SECOND * dt)

        if self.screen_flash > 0:
            self.screen_flash -= dt

        self._tick_powerup_spawns(dt, rect)

        ships = self.living_ships()
        self._tick_boss_pulses(ships, dt)

        # AI + player physics
        for ship in ships:
            if ship.ai_controlled:
                ctrl = self.ai_controllers.get(ship.ship_id)
                if ctrl:
                    rot, thrust, fire = ctrl.update(
                        ship,
                        ships,
                        dt,
                        self.arena.obstacles,
                        self.powerups,
                        self.arena.rect,
                    )
                    ship.apply_rotation(rot, dt)
                    if thrust:
                        ship.apply_thrust(0, dt * thrust)
                    if fire:
                        shots = fire_weapon(ship)
                        if shots:
                            self.projectiles.extend(shots)
                            self.pending_sounds.append("fire_enemy")
            elif ship.is_player and ship.alive:
                rot = 0.0
                if actions.get("rotate_left"):
                    rot -= 1.0
                if actions.get("rotate_right"):
                    rot += 1.0
                ship.apply_rotation(rot, dt)
                if actions.get("thrust"):
                    ship.apply_thrust(0, dt)
                if actions.get("strafe_left"):
                    ship.apply_thrust(-1.57, dt)
                if actions.get("strafe_right"):
                    ship.apply_thrust(1.57, dt)
                if actions.get("fire"):
                    new_shots = fire_weapon(ship)
                    if new_shots:
                        self.projectiles.extend(new_shots)
                        self.pending_sounds.append("fire")

            ship.update_physics(dt, rect)
            if self.arena.ship_hits_obstacle(ship):
                self.arena.resolve_obstacle_collision(ship)
            if ship.alive and ship.thrust_power and vec_len(ship.velocity) > 10:
                self.particles.emit_trail(ship.position, ship.angle, ship.color)
                if vec_len(ship.velocity) > 55:
                    self.particles.emit_trail(ship.position, ship.angle, ship.color)

        # Projectiles
        for proj in self.projectiles:
            old_pos = proj.position
            proj.update(dt)
            new_pos = proj.position
            if self.arena.projectile_hits_obstacle(old_pos, new_pos):
                proj.lifetime = 0
                self.particles.emit_hit(new_pos, (180, 160, 120))
                self.pending_sounds.append("hit")
            else:
                proj.position = wrap_position(new_pos, rect)
            if proj.alive and vec_len(proj.velocity) > 80:
                self.particles.emit_projectile_trail(proj.position, proj.color)
        self.projectiles = [p for p in self.projectiles if p.alive]

        for proj in self.projectiles[:]:
            for ship in ships:
                if projectile_hits_ship(proj, ship):
                    destroyed = ship.take_damage(projectile_hit_damage(proj))
                    self.particles.emit_hit(proj.position, (255, 255, 100))
                    self.pending_sounds.append("hit")
                    proj.lifetime = 0
                    if destroyed:
                        self._on_ship_destroyed(ship)
                    break

        # Ship-ship collision — separate, bounce, then apply ram damage
        for i, a in enumerate(ships):
            for b in ships[i + 1 :]:
                if not ships_collide(a, b):
                    continue
                impact = resolve_ship_collision(a, b)
                if impact < config.MIN_RAM_IMPACT:
                    continue
                a_self, a_tgt = a.ram_damage(impact)
                b_self, b_tgt = b.ram_damage(impact)
                if a.take_damage(a_self + b_tgt * 0.5):
                    self._on_ship_destroyed(a)
                if b.take_damage(b_self + a_tgt * 0.5):
                    self._on_ship_destroyed(b)

        # Powerups
        if self.arena:
            self.arena.resolve_powerup_obstacle_collisions(self.powerups)
        for pu in self.powerups[:]:
            pu.update(dt)
        if self.arena:
            self.arena.resolve_powerup_obstacle_collisions(self.powerups)
        for pu in self.powerups[:]:
            pu.position = wrap_position(pu.position, rect)
            for ship in ships:
                if powerup_collected(pu, ship):
                    ship.apply_powerup(pu.kind.value)
                    self.powerups.remove(pu)
                    self.pending_sounds.append(powerup_sound_name(pu.kind))
                    break
        self.powerups = [p for p in self.powerups if p.alive]

        self.particles.update(dt)

        if self.mode == GameMode.HUMAN:
            self._update_human_mode(dt)
        else:
            self._update_ai_arena(dt)

    def _tick_boss_pulses(self, ships: list[Ship], dt: float) -> None:
        for ship in ships:
            if not ship.alive or not ship.is_boss_evolved:
                continue
            if ship.boss_pulse_flash > 0:
                ship.boss_pulse_flash = max(0.0, ship.boss_pulse_flash - dt)
            ship.boss_pulse_timer -= dt
            if ship.boss_pulse_timer > 0:
                continue
            ship.boss_pulse_timer = config.BOSS_PULSE_COOLDOWN
            ship.boss_pulse_flash = config.BOSS_PULSE_FLASH
            self.pending_sounds.append("boss_pulse")
            self.particles.emit_boss_pulse(ship.position, ship.color)
            for other in ships:
                if other is ship or not other.alive:
                    continue
                dist = vec_len(vec_sub(other.position, ship.position))
                if dist > config.BOSS_PULSE_RADIUS + other.radius:
                    continue
                if other.take_damage(config.BOSS_PULSE_DAMAGE):
                    self._on_ship_destroyed(other)
                else:
                    self.particles.emit_hit(other.position, (255, 130, 90))

    def _spawn_bout_powerups(self) -> None:
        if self.arena is None:
            return
        for _ in range(config.POWERUP_BOUT_START_COUNT):
            if len(self.powerups) >= config.POWERUP_MAX_ON_FIELD:
                break
            self.powerups.append(spawn_powerup_at(self.arena.rect))

    def _tick_powerup_spawns(self, dt: float, rect: tuple[float, float, float, float]) -> None:
        self.powerup_spawn_timer -= dt
        if self.powerup_spawn_timer > 0:
            return
        interval = (
            config.POWERUP_AI_SPAWN_INTERVAL
            if self.mode == GameMode.AI_ARENA
            else config.POWERUP_SPAWN_INTERVAL
        )
        self.powerup_spawn_timer = interval
        if len(self.powerups) >= config.POWERUP_MAX_ON_FIELD:
            return
        pu = maybe_spawn_powerup(rect)
        if pu:
            self.powerups.append(pu)
        if (
            self.mode == GameMode.AI_ARENA
            and len(self.powerups) < config.POWERUP_MAX_ON_FIELD
            and random.random() < 0.35
        ):
            extra = maybe_spawn_powerup(rect)
            if extra:
                self.powerups.append(extra)

    def _on_ship_destroyed(self, ship: Ship) -> None:
        self.particles.emit_explosion(ship.position)
        self.screen_flash = config.SCREEN_FLASH_DURATION
        self.pending_sounds.append("explosion")
        if self.mode == GameMode.AI_ARENA and self.arena:
            ship.champion_wins = 0
            ship.is_boss_evolved = False
            ship.boss_pulse_timer = 0.0
            ship.boss_pulse_flash = 0.0
            ship.apply_champion_bonuses()
            if random.random() < config.POWERUP_DEATH_DROP_CHANCE:
                self.powerups.append(
                    PowerUp(random_powerup_kind(), ship.position)
                )
        if not ship.is_player:
            if self.mode == GameMode.HUMAN:
                self.kills += 1
                self.score += config.SCORE_PER_KILL

    def _update_human_mode(self, dt: float) -> None:
        if self.player and not self.player.alive:
            self.phase = Phase.GAME_OVER
            return
        if self.enemy_spawn_timer > 0:
            self.enemy_spawn_timer = max(0.0, self.enemy_spawn_timer - dt)
            if self.enemy_spawn_timer <= 0:
                self._spawn_wave_enemies()
            return

        living_enemies = [e for e in self.enemies if e.alive]
        if living_enemies or not self.enemies:
            return

        self._heal_ships([self.player] if self.player else [])
        self.score += config.SCORE_PER_WAVE
        self.wave += 1
        self.screen_flash = 0.0
        self.pending_sounds.clear()
        self.projectiles.clear()
        self.enemies.clear()
        self.enemy_spawn_timer = config.WAVE_BREAK_SECONDS
        pu = maybe_spawn_powerup(self.arena.rect) if self.arena else None
        if pu:
            self.powerups.append(pu)

    def _heal_ships(self, ships: list[Ship]) -> None:
        for ship in ships:
            if ship.alive:
                ship.health = ship.max_health

    def _contender_slots(self, living_count: int, champion_wins: int) -> int:
        """Fill the arena to six ships; streak champs face five fresh rivals."""
        return config.AI_ARENA_SHIP_COUNT - living_count

    @staticmethod
    def _champion_bout_invuln(champion_wins: int) -> float:
        if champion_wins <= 0:
            return 0.0
        extra = min(champion_wins, 3) * config.CHAMPION_BOUT_INVULN_PER_WIN
        return config.CHAMPION_BOUT_INVULN + extra

    def _spawn_boss_bout(self) -> None:
        """Easter egg: two evolved bosses after a mutual final-two kill."""
        if self.arena is None:
            return
        x, y, w, h = self.arena.rect
        cx, cy = x + w * 0.5, y + h * 0.5
        offset = min(w, h) * 0.22
        self.projectiles.clear()
        self.pending_sounds.clear()
        self.all_ships = []
        self.ai_controllers.clear()
        variants = [ShipVariant.HEAVY, ShipVariant.HEAVY]
        positions = [(cx - offset, cy), (cx + offset, cy)]
        angles = [0.0, 3.14159265]
        for variant, pos, angle in zip(variants, positions, angles, strict=True):
            ship = Ship.create(
                variant,
                pos,
                angle=angle,
                ship_id=self._next_id(),
                enemy_color=pick_enemy_color(),
            )
            ship.ai_controlled = True
            ship.champion_wins = config.CHAMPION_BOSS_WINS
            ship.is_boss_evolved = True
            ship.apply_champion_bonuses()
            ship.health = ship.max_health
            ship.spawn_invuln = config.CHAMPION_BOUT_INVULN
            self.all_ships.append(ship)
            self.ai_controllers[ship.ship_id] = AIController.for_ship(ship)
        self.enemies = self.all_ships
        self.ai_boss_bout_active = True
        self.ai_boss_bout_cooldown = config.BOSS_BOUT_COOLDOWN_BOUTS
        self.screen_flash = config.BOSS_BOUT_FLASH
        self.pending_sounds.append("boss_pulse")

    def _respawn_ai_opponents(self) -> None:
        if self.arena is None:
            return
        living = [s for s in self.all_ships if s.alive]
        self._heal_ships(living)
        champion_wins = max((s.champion_wins for s in living), default=0)
        slots = self._contender_slots(len(living), champion_wins)
        variants = list(ShipVariant)
        for ship in living:
            if ship.champion_wins > 0:
                ship.spawn_invuln = self._champion_bout_invuln(ship.champion_wins)
        for _ in range(max(0, slots)):
            variant = random.choice(variants)
            ship = Ship.create(
                variant,
                self.arena.spawn_point_inner(),
                ship_id=self._next_id(),
                enemy_color=pick_enemy_color(),
            )
            ship.ai_controlled = True
            living.append(ship)
            self.ai_controllers[ship.ship_id] = AIController.for_ship(ship)
        if champion_wins >= config.CHAMPION_BOUT_SHIELD_WINS and living:
            champ = max(living, key=lambda s: s.champion_wins)
            if champ.champion_wins > 0 and len(self.powerups) < config.POWERUP_MAX_ON_FIELD:
                from combat import PowerUp, PowerUpKind

                self.powerups.append(PowerUp(PowerUpKind.SHIELD, champ.position))
        self.all_ships = living
        self.enemies = self.all_ships
        self.ai_boss_bout_active = False

    def _update_ai_arena(self, dt: float) -> None:
        if self.ai_restart_timer > 0:
            self.ai_restart_timer = max(0.0, self.ai_restart_timer - dt)
            if self.ai_restart_timer <= 0:
                if self.ai_pending_boss_bout:
                    self._spawn_boss_bout()
                    self.ai_pending_boss_bout = False
                else:
                    self._respawn_ai_opponents()
                self._spawn_bout_powerups()
            return

        living = self.living_ships()
        if len(living) <= 1 and any(not s.alive for s in self.all_ships):
            double_ko = len(living) == 0 and self.ai_prev_living_count == 2
            self.all_ships = living
            self.enemies = self.all_ships
            self.ai_controllers = {
                s.ship_id: AIController.for_ship(s) for s in living
            }
            self.projectiles.clear()
            self.pending_sounds.clear()
            self.screen_flash = 0.0
            if living:
                winner = living[0]
                winner.champion_wins += 1
                winner.apply_champion_bonuses()
            self._heal_ships(living)
            self.ai_bout_number += 1
            if (
                double_ko
                and not self.ai_boss_bout_active
                and self.ai_boss_bout_cooldown <= 0
            ):
                self.ai_pending_boss_bout = True
                self.ai_restart_timer = config.BOSS_BOUT_RESTART_DELAY
            else:
                if self.ai_boss_bout_cooldown > 0:
                    self.ai_boss_bout_cooldown -= 1
                self.ai_restart_timer = config.AI_ARENA_RESTART_DELAY
            self.ai_prev_living_count = len(living)
            return

        self.ai_prev_living_count = len(living)

    def toggle_ai_arena(self) -> GameMode:
        if self.mode == GameMode.HUMAN:
            self.start_ai_arena()
            return GameMode.AI_ARENA
        self.start_human(self.player_variant)
        return GameMode.HUMAN