"""Veil — entry point and pygame rendering."""

from __future__ import annotations

import math
import sys
from enum import Enum

import pygame

import config
from arena import Arena
from utils import vec_add, vec_from_angle, vec_len
from controls import ACTION_LABELS, Action, BindingMap
from game import GameMode, GameState, Phase
from scores import HighScoreTable
from settings import GameSettings
from ship import ShipVariant
from audio import SoundManager

# Colors
BG = (0, 0, 0)
TEXT = (220, 220, 230)
ACCENT = (80, 200, 255)
MENU_BG = (8, 8, 14)


def _poly_centroid(points: list[tuple[int, int]]) -> tuple[float, float]:
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _shrink_poly(
    points: list[tuple[int, int]],
    center: tuple[float, float],
    scale: float,
) -> list[tuple[int, int]]:
    cx, cy = center
    return [
        (int(cx + (p[0] - cx) * scale), int(cy + (p[1] - cy) * scale))
        for p in points
    ]


class UiState(str, Enum):
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    CONTROLS = "controls"
    GAME_OVER = "game_over"


class VeilApp:
    def __init__(self) -> None:
        pygame.mixer.pre_init(44100, -16, 12, 512)
        pygame.init()
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.screen = pygame.display.set_mode(
            (config.DEFAULT_WIDTH, config.DEFAULT_HEIGHT), pygame.RESIZABLE
        )
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)
        self.font_lg = pygame.font.SysFont("consolas", 36)
        self.font_sm = pygame.font.SysFont("consolas", 16)

        self.state = GameState()
        self.state.arena = Arena.from_window(*self.screen.get_size())
        self.ui = UiState.MENU
        self.bindings = BindingMap()
        self.bindings.load()
        self.settings = GameSettings()
        self.settings.load()
        self.scores = HighScoreTable()
        self.scores.load()
        self.audio = SoundManager()
        self.audio.init()
        self.audio.enabled = self.settings.sounds_enabled

        self.rebind_action: Action | None = None
        self._ctrl_idx = Action.ROTATE_LEFT
        self._ctrl_sounds_selected = False

        self.menu_selection = 1  # 0=light, 1=balanced, 2=heavy, 3=ai arena, 4=quit
        self.pause_selection = 0
        self.game_over_timer = 0.0
        self._game_over_saved = False

    def resize(self, size: tuple[int, int]) -> None:
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.state.arena = Arena.from_window(*size)

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(config.TARGET_FPS) / 1000.0
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.resize(event.size)
                else:
                    self.handle_event(event)

            self.update(dt)
            self.draw()
        pygame.quit()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.ui == UiState.MENU:
            self._menu_event(event)
        elif self.ui == UiState.PAUSED:
            self._pause_event(event)
        elif self.ui == UiState.CONTROLS:
            self._controls_event(event)
        elif self.ui == UiState.GAME_OVER:
            self._game_over_event(event)
        elif self.ui == UiState.PLAYING:
            self._playing_event(event)

    def _menu_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.menu_selection = (self.menu_selection - 1) % 5
                self.audio.play("ui")
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.menu_selection = (self.menu_selection + 1) % 5
                self.audio.play("ui")
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.menu_selection == 4:
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                    return
                self._game_over_saved = False
                if self.menu_selection == 3:
                    self.state.start_ai_arena()
                else:
                    variants = [
                        ShipVariant.LIGHT,
                        ShipVariant.BALANCED,
                        ShipVariant.HEAVY,
                    ]
                    self.state.start_human(variants[self.menu_selection])
                self.ui = UiState.PLAYING
            elif event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _playing_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.ui = UiState.PAUSED
            self.pause_selection = 0
            self.audio.play("ui")
            return
        action = self.bindings.action_down(event)
        if action == Action.PAUSE:
            self.ui = UiState.PAUSED
            self.pause_selection = 0
            self.audio.play("ui")
        elif action == Action.QUIT:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif action == Action.TOGGLE_AI_ARENA:
            self.state.toggle_ai_arena()
            self.ui = UiState.PLAYING

    def _pause_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.pause_selection = (self.pause_selection - 1) % 4
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.pause_selection = (self.pause_selection + 1) % 4
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._pause_activate()
            elif event.key == pygame.K_ESCAPE:
                self.ui = UiState.PLAYING
            elif event.key == pygame.K_p:
                self.ui = UiState.PLAYING

    def _pause_activate(self) -> None:
        opts = ["resume", "controls", "ai_arena", "quit"]
        choice = opts[self.pause_selection]
        if choice == "resume":
            self.ui = UiState.PLAYING
        elif choice == "controls":
            self.ui = UiState.CONTROLS
            self.rebind_action = None
            self._ctrl_sounds_selected = False
            self._ctrl_idx = Action.ROTATE_LEFT
        elif choice == "ai_arena":
            self.state.toggle_ai_arena()
            self.ui = UiState.PLAYING
            self.audio.play("ui")
        elif choice == "quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _controls_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.ui = UiState.PAUSED
                return
            if event.key == pygame.K_r:
                self.bindings.restore_defaults()
                self.bindings.save()
                self.audio.play("ui")
                return
            if self.rebind_action is None:
                if event.key in (pygame.K_UP, pygame.K_w):
                    if self._ctrl_sounds_selected:
                        self._ctrl_sounds_selected = False
                        self._ctrl_idx = list(Action)[-1]
                    else:
                        idx = list(Action).index(self._ctrl_idx)
                        if idx == 0:
                            self._ctrl_sounds_selected = True
                        else:
                            self._ctrl_idx = list(Action)[idx - 1]
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    if self._ctrl_sounds_selected:
                        self._ctrl_sounds_selected = False
                        self._ctrl_idx = list(Action)[0]
                    else:
                        idx = list(Action).index(self._ctrl_idx)
                        if idx == len(Action) - 1:
                            self._ctrl_sounds_selected = True
                        else:
                            self._ctrl_idx = list(Action)[idx + 1]
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self._ctrl_sounds_selected:
                        enabled = self.settings.toggle_sounds()
                        self.audio.enabled = enabled
                        self.audio.play("ui")
                    else:
                        self.rebind_action = self._ctrl_idx
            return
        binding = self.bindings.binding_from_event(event)
        if binding and self.rebind_action:
            err = self.bindings.set_binding(self.rebind_action, binding)
            if err is None:
                self.bindings.save()
                self.audio.play("ui")
            self.rebind_action = None

    def _return_to_menu(self) -> None:
        self.ui = UiState.MENU
        self.state.phase = Phase.MENU
        self._game_over_saved = False

    def _game_over_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self._return_to_menu()
            elif event.key in (pygame.K_q, pygame.K_x):
                pygame.event.post(pygame.event.Event(pygame.QUIT))
        action = self.bindings.action_down(event)
        if action == Action.QUIT:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def update(self, dt: float) -> None:
        if self.ui != UiState.PLAYING:
            if self.ui == UiState.GAME_OVER and not self._game_over_saved:
                self.scores.add(
                    self.state.score,
                    self.state.wave,
                    self.state.player_variant.value,
                )
                self.audio.play("explosion")
                self._game_over_saved = True
            return

        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed()
        held = self.bindings.action_held(keys, mouse)
        actions = {
            "rotate_left": Action.ROTATE_LEFT in held,
            "rotate_right": Action.ROTATE_RIGHT in held,
            "thrust": Action.THRUST in held,
            "strafe_left": Action.STRAFE_LEFT in held,
            "strafe_right": Action.STRAFE_RIGHT in held,
            "fire": Action.FIRE in held,
        }
        self.state.update(dt, actions)
        self.audio.tick(dt)
        if self.state.phase == Phase.PLAYING:
            self.audio.play_batch(self.state.pending_sounds)

        if self.state.phase == Phase.GAME_OVER:
            self.ui = UiState.GAME_OVER
            if not self._game_over_saved:
                self.scores.add(
                    self.state.score,
                    self.state.wave,
                    self.state.player_variant.value,
                )
                self.audio.play("explosion")
                self._game_over_saved = True

    def draw(self) -> None:
        w, h = self.screen.get_size()
        self.screen.fill(BG)

        if self.state.arena:
            self._draw_arena()

        if self.ui == UiState.MENU:
            self._draw_menu()
        elif self.ui == UiState.GAME_OVER:
            self._draw_game()
            self._draw_game_over()
        elif self.ui == UiState.PAUSED:
            self._draw_game()
            self._draw_pause_menu()
        elif self.ui == UiState.CONTROLS:
            self._draw_controls()
        else:
            self._draw_game()
            self._draw_hud()

        pygame.display.flip()

    def _draw_arena(self) -> None:
        arena = self.state.arena
        if not arena:
            return
        x, y, aw, ah = (int(v) for v in arena.rect)
        import random as _random

        for obs in arena.obstacles:
            verts = [(int(v[0]), int(v[1])) for v in obs.vertices]
            if len(verts) < 3:
                continue
            cx, cy = int(obs.center[0]), int(obs.center[1])
            shadow = [(v[0] + 2, v[1] + 2) for v in verts]
            pygame.draw.polygon(self.screen, (18, 16, 14), shadow, 0)
            pygame.draw.polygon(self.screen, (72, 68, 62), verts, 0)
            pygame.draw.polygon(self.screen, (118, 112, 100), verts, 2)
            rng = _random.Random(obs.crater_seed)
            for _ in range(4):
                cr = rng.randint(2, 4)
                ox = cx + rng.randint(-int(obs.radius * 0.45), int(obs.radius * 0.45))
                oy = cy + rng.randint(-int(obs.radius * 0.45), int(obs.radius * 0.45))
                pygame.draw.circle(self.screen, (45, 42, 38), (ox, oy), cr)
        twinkle_t = pygame.time.get_ticks() * 0.001
        sw, sh = self.screen.get_size()
        for sx, sy, base, phase, speed, amp in arena.stars:
            bright = base
            if amp > 0:
                bright = base + amp * math.sin(twinkle_t * speed + phase)
                bright = max(0.15, min(1.0, bright))
            c = int(80 + 120 * bright)
            self.screen.set_at((int(sx) % sw, int(sy) % sh), (c, c, c))

    def _draw_game(self) -> None:
        if self.state.screen_flash > 0:
            flash = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            alpha = int(80 * self.state.screen_flash / 0.15)
            flash.fill((255, 255, 255, alpha))
            self.screen.blit(flash, (0, 0))

        for p in self.state.particles.particles:
            alpha = int(255 * (p.lifetime / p.max_lifetime))
            c = (*p.color[:3],)
            pygame.draw.circle(
                self.screen, c, (int(p.position[0]), int(p.position[1])), int(p.size)
            )

        for pu in self.state.powerups:
            self._draw_powerup(pu)

        for proj in self.state.projectiles:
            pygame.draw.line(
                self.screen,
                proj.color,
                (int(proj.position[0]), int(proj.position[1])),
                (
                    int(proj.position[0] - proj.velocity[0] * 0.03),
                    int(proj.position[1] - proj.velocity[1] * 0.03),
                ),
                2,
            )

        ships = self.state.living_ships()
        if self.state.player and self.state.player.alive and self.state.player not in ships:
            ships = ships + [self.state.player]
        for ship in ships:
            if not ship.alive:
                continue
            self._draw_ship(ship)
            if ship.shield_timer > 0:
                pygame.draw.circle(
                    self.screen,
                    (100, 220, 255),
                    (int(ship.position[0]), int(ship.position[1])),
                    int(ship.radius + 4),
                    1,
                )
            # Health bar
            if ship.max_health > 0:
                ratio = ship.health / ship.max_health
                bx = int(ship.position[0] - 15)
                by = int(ship.position[1] - ship.radius - 10)
                pygame.draw.rect(self.screen, (60, 60, 60), (bx, by, 30, 3))
                pygame.draw.rect(self.screen, (100, 255, 100), (bx, by, int(30 * ratio), 3))

    def _draw_powerup(self, pu) -> None:
        import math

        from combat import POWERUP_COLORS, PowerUpKind

        x, y = int(pu.position[0]), int(pu.position[1])
        col = POWERUP_COLORS.get(pu.kind, (200, 200, 200))
        pulse = 1.0 + 0.12 * math.sin(pu.lifetime * 5.0)
        glow = tuple(max(0, int(c * 0.35)) for c in col)
        pygame.draw.circle(self.screen, glow, (x, y), int(16 * pulse))
        pygame.draw.circle(self.screen, col, (x, y), int(11 * pulse), 2)

        if pu.kind == PowerUpKind.SHIELD:
            pts = [
                (x, y - 9), (x + 8, y - 3), (x + 8, y + 5),
                (x, y + 9), (x - 8, y + 5), (x - 8, y - 3),
            ]
            fill = tuple(max(0, int(c * 0.4)) for c in col)
            pygame.draw.polygon(self.screen, fill, pts, 0)
            pygame.draw.polygon(self.screen, col, pts, 2)
            pygame.draw.arc(self.screen, col, (x - 7, y - 8, 14, 14), 0.4, 2.7, 2)
        elif pu.kind == PowerUpKind.FIRE_RATE:
            bolt = [(x - 2, y - 9), (x + 4, y - 1), (x + 1, y - 1), (x + 3, y + 9), (x - 3, y + 1), (x, y + 1)]
            pygame.draw.polygon(self.screen, col, bolt, 0)
            pygame.draw.polygon(self.screen, (255, 255, 255), bolt, 1)
        else:
            for angle in (-0.5, 0.0, 0.5):
                dx = int(math.cos(angle) * 10)
                dy = int(math.sin(angle) * 10)
                pygame.draw.line(self.screen, col, (x, y), (x + dx, y + dy), 3)
            pygame.draw.circle(self.screen, (255, 255, 255), (x, y), 3)

    def _draw_ship(self, ship) -> None:
        pts = [(int(p[0]), int(p[1])) for p in ship.hull_points()]
        if len(pts) < 3:
            return
        if ship.is_player:
            fill = tuple(max(0, c - 30) for c in ship.color)
            aux_fill = tuple(max(0, c - 55) for c in ship.color)
            highlight = tuple(min(255, c + 35) for c in ship.color)
            outline = (180, 230, 255)
            canopy = (120, 210, 255)
            exhaust = (60, 180, 255)
            nozzle = (40, 140, 220)
            glow_col = (40, 100, 180)
        else:
            fill = tuple(max(0, int(c * 0.75)) for c in ship.color)
            aux_fill = tuple(max(0, int(c * 0.5)) for c in ship.color)
            highlight = tuple(min(255, int(c * 0.95)) for c in ship.color)
            outline = tuple(min(255, int(c * 1.1 + 18)) for c in ship.color)
            canopy = tuple(min(255, int(c * 0.88)) for c in ship.color)
            exhaust = tuple(max(0, int(c * 0.65)) for c in ship.color)
            nozzle = tuple(max(0, int(c * 0.42)) for c in ship.color)
            glow_col = tuple(max(0, int(c * 0.32)) for c in ship.color)
            nose_line = tuple(min(255, int(c * 1.05 + 35)) for c in ship.color)
        cx, cy = int(ship.position[0]), int(ship.position[1])
        if ship.is_boss_evolved and ship.boss_pulse_flash > 0:
                progress = 1.0 - ship.boss_pulse_flash / config.BOSS_PULSE_FLASH
                ring_r = int(config.BOSS_PULSE_RADIUS * progress)
                ring = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(
                    ring,
                    (255, 140, 90, int(180 * (1.0 - progress))),
                    (ring_r + 2, ring_r + 2),
                    ring_r,
                    3,
                )
                self.screen.blit(ring, (cx - ring_r - 2, cy - ring_r - 2))
        glow_surf = pygame.Surface((64, 64), pygame.SRCALPHA)
        glow_alpha = 70 if ship.is_boss_evolved else 40
        glow_size = 24 if ship.is_boss_evolved else 18
        pygame.draw.circle(glow_surf, (*glow_col, glow_alpha), (32, 32), glow_size)
        self.screen.blit(glow_surf, (cx - 32, cy - 32))
        shadow = [(int(p[0] + 3), int(p[1] + 3)) for p in pts]
        shadow_surf = pygame.Surface(
            (self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA
        )
        pygame.draw.polygon(shadow_surf, (0, 0, 0, 55), shadow, 0)
        self.screen.blit(shadow_surf, (0, 0))
        centroid = _poly_centroid(pts)
        rim_pts = _shrink_poly(pts, centroid, 1.04)
        rim_col = tuple(min(255, int(c * 1.15 + 22)) for c in outline)
        pygame.draw.polygon(self.screen, rim_col, rim_pts, 1)
        for aux in ship.aux_hull_points():
            aux_pts = [(int(p[0]), int(p[1])) for p in aux]
            if len(aux_pts) >= 3:
                pygame.draw.polygon(self.screen, aux_fill, aux_pts, 0)
                pygame.draw.polygon(self.screen, outline, aux_pts, 1)
        pygame.draw.polygon(self.screen, fill, pts, 0)
        inner_pts = _shrink_poly(pts, centroid, 0.70)
        inner_fill = tuple(max(0, int(c * 0.42)) for c in fill)
        pygame.draw.polygon(self.screen, inner_fill, inner_pts, 0)
        hi = [(int(p[0]), int(p[1])) for p in ship.highlight_points()]
        if len(hi) >= 3:
            pygame.draw.polygon(self.screen, highlight, hi, 0)
            hi_rim = _shrink_poly(hi, _poly_centroid(hi), 0.88)
            hi_edge = tuple(min(255, int(c * 1.08 + 18)) for c in highlight)
            pygame.draw.polygon(self.screen, hi_edge, hi_rim, 1)
        pygame.draw.polygon(self.screen, outline, pts, 2)
        gleam_pts = [(p[0] - 1, p[1] - 1) for p in pts]
        gleam_col = tuple(min(255, int(c * 0.55 + 40)) for c in outline)
        pygame.draw.polygon(self.screen, gleam_col, gleam_pts, 1)
        na, nb = ship.nose_line()
        nose_col = (240, 250, 255) if ship.is_player else nose_line
        pygame.draw.line(
            self.screen,
            tuple(max(0, int(c * 0.55)) for c in nose_col),
            (int(na[0]), int(na[1])),
            (int(nb[0]), int(nb[1])),
            3,
        )
        pygame.draw.line(
            self.screen,
            nose_col,
            (int(na[0]), int(na[1])),
            (int(nb[0]), int(nb[1])),
            1,
        )
        panel_col = tuple(max(0, int(c * 0.55)) for c in outline)
        for a, b in ship.panel_lines():
            pygame.draw.line(
                self.screen,
                panel_col,
                (int(a[0]), int(a[1])),
                (int(b[0]), int(b[1])),
                1,
            )
            mid = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            seg = 0.22 * math.hypot(b[0] - a[0], b[1] - a[1])
            if seg > 2:
                dx = (b[0] - a[0]) / max(math.hypot(b[0] - a[0], b[1] - a[1]), 1.0)
                dy = (b[1] - a[1]) / max(math.hypot(b[0] - a[0], b[1] - a[1]), 1.0)
                p1 = (int(mid[0] - dx * seg), int(mid[1] - dy * seg))
                p2 = (int(mid[0] + dx * seg), int(mid[1] + dy * seg))
                pygame.draw.line(self.screen, outline, p1, p2, 2)
        for a, b in ship.fin_lines():
            pygame.draw.line(
                self.screen,
                outline,
                (int(a[0]), int(a[1])),
                (int(b[0]), int(b[1])),
                2,
            )
        wc = ship.window_center()
        wr = int(ship.window_radius())
        wcx, wcy = int(wc[0]), int(wc[1])
        pygame.draw.circle(self.screen, (8, 10, 16), (wcx, wcy), wr + 1)
        pygame.draw.circle(self.screen, (12, 16, 24), (wcx, wcy), wr)
        pygame.draw.circle(self.screen, canopy, (wcx, wcy), wr - 1)
        pygame.draw.circle(
            self.screen,
            tuple(max(0, int(c * 0.55)) for c in canopy),
            (wcx, wcy),
            max(1, wr - 3),
            1,
        )
        pygame.draw.circle(self.screen, (240, 250, 255), (wcx, wcy), wr, 1)
        glint = vec_add(wc, vec_from_angle(ship.angle + 0.4, wr * 0.35))
        pygame.draw.circle(self.screen, (220, 240, 255), (int(glint[0]), int(glint[1])), 2)
        pygame.draw.circle(self.screen, (255, 255, 255), (int(glint[0]), int(glint[1])), 1)
        nozzles = ship.engine_nozzles()
        nr = 4 if ship.variant.value == "heavy" else 3
        for nz in nozzles:
            pygame.draw.circle(self.screen, (16, 16, 22), (int(nz[0]), int(nz[1])), nr + 1)
            pygame.draw.circle(self.screen, nozzle, (int(nz[0]), int(nz[1])), nr)
            pygame.draw.circle(self.screen, (20, 20, 28), (int(nz[0]), int(nz[1])), max(1, nr - 2))
        speed = vec_len(ship.velocity)
        if speed > 20:
            glow = 5 + int(min(speed, 120) / 25)
            for nz in nozzles:
                plume = pygame.Surface((glow * 4 + 4, glow * 4 + 4), pygame.SRCALPHA)
                pygame.draw.circle(
                    plume,
                    (*exhaust, 70),
                    (glow * 2 + 2, glow * 2 + 2),
                    glow,
                )
                self.screen.blit(
                    plume,
                    (int(nz[0]) - glow * 2 - 2, int(nz[1]) - glow * 2 - 2),
                )
                pygame.draw.circle(
                    self.screen, exhaust, (int(nz[0]), int(nz[1])), glow, 1
                )
            el, er = ship.engine_points()
            pygame.draw.line(
                self.screen,
                exhaust,
                (int(el[0]), int(el[1])),
                (int(er[0]), int(er[1])),
                2,
            )

    def _draw_star_glyph(self, cx: int, cy: int, size: int = 5) -> None:
        points: list[tuple[int, int]] = []
        for i in range(10):
            radius = size if i % 2 == 0 else max(2, int(size * 0.45))
            angle = -math.pi / 2 + i * math.pi / 5
            points.append(
                (int(cx + math.cos(angle) * radius), int(cy + math.sin(angle) * radius))
            )
        pygame.draw.polygon(self.screen, ACCENT, points)

    def _blit_hud_win_line(
        self, x: int, y: int, prefix: str, wins: int, suffix: str = ""
    ) -> None:
        surf = self.font.render(prefix, True, TEXT)
        self.screen.blit(surf, (x, y))
        cursor = x + surf.get_width() + 4
        self._draw_star_glyph(cursor + 5, y + 11)
        tail = self.font.render(f"{wins}{suffix}", True, TEXT)
        self.screen.blit(tail, (cursor + 14, y))

    def _ai_hud_entries(self) -> list[tuple]:
        entries: list[tuple] = [
            ("plain", f"Veil  |  Bout {self.state.ai_bout_number}")
        ]
        contenders = sorted(
            self.state.all_ships,
            key=lambda s: s.champion_wins,
            reverse=True,
        )
        top = [s for s in contenders if s.champion_wins > 0][:3]
        if top:
            champ = top[0]
            if champ.is_boss_evolved:
                label = f"BOSS: {champ.variant.value} "
            elif champ.champion_wins >= config.CHAMPION_BOSS_WINS - 1:
                label = f"Ascendant: {champ.variant.value} "
            else:
                label = f"Champion: {champ.variant.value} "
            entries.append(("wins", label, champ.champion_wins, ""))
            if len(top) > 1:
                others = "  |  ".join(
                    f"{s.variant.value} x{s.champion_wins}" for s in top[1:]
                )
                entries.append(("plain", f"Contenders: {others}"))
        if self.state.ai_restart_timer > 0:
            living = self.state.living_ships()
            winner = living[0] if living else None
            if winner:
                tag = "BOSS" if winner.is_boss_evolved else winner.variant.value
                entries.append(
                    (
                        "wins",
                        f"Last bout: {tag} ",
                        winner.champion_wins,
                        f" - next in {self.state.ai_restart_timer:.1f}s",
                    )
                )
        return entries

    def _draw_hud(self) -> None:
        if self.state.mode == GameMode.AI_ARENA:
            entries = self._ai_hud_entries()
            for i, entry in enumerate(entries):
                y = 16 + i * 24
                if entry[0] == "wins":
                    self._blit_hud_win_line(16, y, entry[1], entry[2], entry[3])
                else:
                    surf = self.font.render(entry[1], True, TEXT)
                    self.screen.blit(surf, (16, y))
        else:
            lines = [
                f"Veil  |  Human  |  Score: {self.state.score}",
                f"Wave: {self.state.wave}  |  Kills: {self.state.kills}",
            ]
            if self.state.enemy_spawn_timer > 0:
                lines.append(f"Next wave in {self.state.enemy_spawn_timer:.1f}s")
            for i, line in enumerate(lines):
                surf = self.font.render(line, True, TEXT)
                self.screen.blit(surf, (16, 16 + i * 24))

    def _draw_menu(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        title = self.font_lg.render("VEIL", True, ACCENT)
        self.screen.blit(title, title.get_rect(center=(self.screen.get_width() // 2, 120)))
        subtitle = self.font.render("Minimal Vector Skirmish", True, TEXT)
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.screen.get_width() // 2, 165)))
        prompt = self.font.render("Select your ship — Up/Down, Enter", True, TEXT)
        self.screen.blit(prompt, prompt.get_rect(center=(self.screen.get_width() // 2, 220)))
        names = ["Light Fighter", "Balanced Interceptor", "Heavy Gunship"]
        descs = [
            "Fast, agile — ramming is dangerous",
            "All-rounder",
            "Slow, tough — ramming works",
        ]
        for i, (name, desc) in enumerate(zip(names, descs)):
            color = ACCENT if i == self.menu_selection else TEXT
            prefix = "> " if i == self.menu_selection else "  "
            surf = self.font.render(f"{prefix}{name}", True, color)
            self.screen.blit(surf, (self.screen.get_width() // 2 - 160, 280 + i * 50))
            ds = self.font_sm.render(desc, True, (140, 140, 150))
            self.screen.blit(ds, (self.screen.get_width() // 2 - 160, 305 + i * 50))
        ai_color = ACCENT if self.menu_selection == 3 else TEXT
        ai_prefix = "> " if self.menu_selection == 3 else "  "
        ai_surf = self.font.render(f"{ai_prefix}AI Arena", True, ai_color)
        self.screen.blit(ai_surf, (self.screen.get_width() // 2 - 160, 430))
        ai_desc = self.font_sm.render(
            "Watch ships fight — champion streaks and boss evolutions", True, (140, 140, 150)
        )
        self.screen.blit(ai_desc, (self.screen.get_width() // 2 - 160, 455))
        quit_color = ACCENT if self.menu_selection == 4 else TEXT
        quit_prefix = "> " if self.menu_selection == 4 else "  "
        quit_surf = self.font.render(f"{quit_prefix}Quit", True, quit_color)
        self.screen.blit(quit_surf, (self.screen.get_width() // 2 - 160, 490))

    def _draw_pause_menu(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        title = self.font_lg.render("PAUSED", True, ACCENT)
        self.screen.blit(title, title.get_rect(center=(self.screen.get_width() // 2, 200)))
        items = ["Resume", "Controls", "AI Arena Mode", "Quit"]
        for i, item in enumerate(items):
            color = ACCENT if i == self.pause_selection else TEXT
            prefix = "> " if i == self.pause_selection else "  "
            surf = self.font.render(f"{prefix}{item}", True, color)
            self.screen.blit(surf, surf.get_rect(center=(self.screen.get_width() // 2, 300 + i * 40)))

    def _draw_controls(self) -> None:
        self.screen.fill(MENU_BG)
        title = self.font_lg.render("CONTROLS", True, ACCENT)
        self.screen.blit(title, (40, 30))
        hint = self.font_sm.render(
            "Up/Down select — Enter rebind/toggle — R restore defaults — Esc back",
            True,
            (140, 140, 150),
        )
        self.screen.blit(hint, (40, 80))
        snd_label = "ON" if self.settings.sounds_enabled else "OFF"
        snd_color = ACCENT if self._ctrl_sounds_selected and not self.rebind_action else TEXT
        snd_prefix = "> " if self._ctrl_sounds_selected and not self.rebind_action else "  "
        snd_surf = self.font.render(f"{snd_prefix}Sounds: {snd_label}", True, snd_color)
        self.screen.blit(snd_surf, (60, 130))
        if self.rebind_action:
            msg = self.font.render(
                f"Press key, mouse button, or wheel for {ACTION_LABELS[self.rebind_action]}...",
                True,
                (255, 220, 100),
            )
            self.screen.blit(msg, (40, 120))
        idx = self._ctrl_idx
        for i, action in enumerate(Action):
            b = self.bindings.bindings[action]
            color = ACCENT if action == idx and not self.rebind_action else TEXT
            prefix = "> " if action == idx and not self.rebind_action else "  "
            line = f"{prefix}{ACTION_LABELS[action]}: {b.label}"
            surf = self.font.render(line, True, color)
            self.screen.blit(surf, (60, 170 + i * 32))

    def _draw_game_over(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        title = self.font_lg.render("GAME OVER", True, (255, 80, 60))
        self.screen.blit(title, title.get_rect(center=(self.screen.get_width() // 2, 200)))
        score = self.font.render(f"Final Score: {self.state.score}", True, TEXT)
        self.screen.blit(score, score.get_rect(center=(self.screen.get_width() // 2, 260)))
        wave = self.font.render(f"Wave Reached: {self.state.wave}", True, TEXT)
        self.screen.blit(wave, wave.get_rect(center=(self.screen.get_width() // 2, 295)))
        hs_title = self.font.render("High Scores", True, ACCENT)
        self.screen.blit(hs_title, hs_title.get_rect(center=(self.screen.get_width() // 2, 350)))
        for i, entry in enumerate(self.scores.entries[:5]):
            line = f"{entry.score} — wave {entry.wave} ({entry.ship})"
            surf = self.font_sm.render(line, True, TEXT)
            self.screen.blit(
                surf, surf.get_rect(center=(self.screen.get_width() // 2, 385 + i * 24))
            )
        prompt = self.font.render(
            "Enter / Esc: menu   |   Q: quit", True, (140, 140, 150)
        )
        self.screen.blit(prompt, prompt.get_rect(center=(self.screen.get_width() // 2, 520)))


def main() -> None:
    app = VeilApp()
    app.run()


if __name__ == "__main__":
    main()