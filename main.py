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
from audio import MusicManager, SoundManager

# Colors
BG = (0, 0, 0)
TEXT = (220, 220, 230)
ACCENT = (80, 200, 255)
MENU_BG = (8, 8, 14)
SETTINGS_ROWS = ("sfx", "music", "work", "borderless")


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


_NEBULA_PUFF_BLOBS = (
    (0.0, 0.0, 0.44, 1.0),
    (0.2, -0.14, 0.3, 0.68),
    (-0.24, 0.16, 0.26, 0.58),
    (0.1, 0.22, 0.2, 0.45),
    (-0.12, -0.2, 0.17, 0.38),
    (0.28, 0.08, 0.13, 0.3),
    (-0.06, 0.05, 0.11, 0.25),
)


_HULL_GRAY = (70, 72, 76)
_HULL_GRAY_DARK = (48, 50, 54)
_HULL_GRAY_INNER = (38, 40, 44)
_HULL_GRAY_RIM = (112, 115, 120)
_HULL_GRAY_PANEL = (88, 90, 94)


def _ship_paint(ship) -> dict[str, tuple[int, ...]]:
    """Grayscale hull with faction color reserved for highlights."""
    accent = ship.color
    if ship.is_player:
        accent = (90, 195, 255)
    canopy = tuple(min(255, int(c * 0.82 + 28)) for c in accent)
    exhaust = tuple(max(0, int(c * 0.62)) for c in accent)
    return {
        "fill": _HULL_GRAY,
        "aux_fill": _HULL_GRAY_DARK,
        "inner_fill": _HULL_GRAY_INNER,
        "highlight": accent,
        "outline": _HULL_GRAY_RIM,
        "rim": _HULL_GRAY_RIM,
        "panel": _HULL_GRAY_PANEL,
        "canopy": canopy,
        "exhaust": exhaust,
        "nozzle": _HULL_GRAY_DARK,
        "nose_line": accent,
        "glow_col": tuple(max(0, int(c * 0.22)) for c in accent),
        "gleam": tuple(min(255, int(c * 0.35 + 70)) for c in accent),
        "hi_edge": tuple(min(255, int(c * 0.9 + 18)) for c in accent),
    }


def _nebula_puff(
    size: tuple[int, int],
    color: tuple[int, int, int],
    alpha: int,
) -> pygame.Surface:
    """Soft oblong cloud from overlapping blobs (fractal-ish, not one circle)."""
    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    cx, cy = w * 0.5, h * 0.5
    base = min(w, h)
    for ox_frac, oy_frac, r_frac, a_mult in _NEBULA_PUFF_BLOBS:
        radius = max(2, int(base * r_frac))
        blob_alpha = max(0, min(255, int(alpha * a_mult)))
        pygame.draw.circle(
            surf,
            (*color, blob_alpha),
            (int(cx + ox_frac * w), int(cy + oy_frac * h)),
            radius,
        )
    return surf


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
        self.settings = GameSettings()
        self.settings.load()
        start_size = (self.settings.window_width, self.settings.window_height)
        self.screen = pygame.display.set_mode(start_size, self._window_flags())
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 20)
        self.font_lg = pygame.font.SysFont("consolas", 36)
        self.font_sm = pygame.font.SysFont("consolas", 16)

        self.state = GameState()
        self.state.arena = Arena.from_window(*self.screen.get_size())
        self.ui = UiState.MENU
        self.bindings = BindingMap()
        self.bindings.load()
        self.scores = HighScoreTable()
        self.scores.load()
        self.audio = SoundManager()
        self.audio.init()
        self.audio.sfx_volume = self.settings.sfx_volume
        self.music = MusicManager()
        self.music.init()
        self.music.set_volume(self.settings.music_volume)

        self.rebind_action: Action | None = None
        self._ctrl_idx = Action.ROTATE_LEFT
        self._ctrl_settings_row: str | None = None

        self.menu_selection = 1  # 0=light, 1=balanced, 2=heavy, 3=ai arena, 4=quit
        self.pause_selection = 0
        self.game_over_timer = 0.0
        self._game_over_saved = False
        self._vignette_size: tuple[int, int] | None = None
        self._vignette_surface: pygame.Surface | None = None
        self._nebula_puff_size: tuple[int, int] | None = None
        self._nebula_puffs: list[pygame.Surface] = []
        self._borderless_resize: str | None = None
        self._borderless_resize_anchor: tuple[int, int, int, int] | None = None
        self._borderless_cursor: str | None = None

    def _window_flags(self) -> int:
        flags = pygame.RESIZABLE
        if self.settings.borderless_window:
            flags |= pygame.NOFRAME
        return flags

    def _apply_display_mode(self, size: tuple[int, int] | None = None) -> None:
        if size is None:
            size = self.screen.get_size()
        self.screen = pygame.display.set_mode(size, self._window_flags())
        self.state.arena = Arena.from_window(*size)
        self.settings.remember_window_size(*size)
        self._vignette_size = None
        self._vignette_surface = None
        self._nebula_puff_size = None
        self._nebula_puffs = []

    def _ensure_nebula_puffs(self, sw: int, sh: int) -> list[pygame.Surface]:
        if self._nebula_puff_size == (sw, sh) and self._nebula_puffs:
            return self._nebula_puffs
        base = int(max(sw, sh) * 0.34)
        self._nebula_puffs = [
            _nebula_puff((int(base * 1.45), int(base * 0.52)), (14, 18, 30), 11),
            _nebula_puff((int(base * 0.82), int(base * 0.68)), (16, 20, 32), 10),
            _nebula_puff((int(base * 1.2), int(base * 0.42)), (12, 16, 28), 9),
        ]
        self._nebula_puff_size = (sw, sh)
        return self._nebula_puffs

    def resize(self, size: tuple[int, int]) -> None:
        self._apply_display_mode(size)

    def _clamp_window_size(self, width: int, height: int) -> tuple[int, int]:
        return (
            max(config.WINDOW_MIN_WIDTH, min(config.WINDOW_MAX_WIDTH, int(width))),
            max(config.WINDOW_MIN_HEIGHT, min(config.WINDOW_MAX_HEIGHT, int(height))),
        )

    def _set_window_size(self, width: int, height: int) -> None:
        size = self._clamp_window_size(width, height)
        if size != self.screen.get_size():
            self._apply_display_mode(size)

    def _nudge_window_size(self, delta_w: int, delta_h: int) -> None:
        w, h = self.settings.adjust_window_size(delta_w, delta_h)
        self._set_window_size(w, h)

    def _borderless_resize_zone(self, pos: tuple[int, int]) -> str | None:
        if not self.settings.borderless_window:
            return None
        w, h = self.screen.get_size()
        x, y = pos
        margin = config.BORDERLESS_RESIZE_MARGIN
        on_right = x >= w - margin
        on_bottom = y >= h - margin
        if on_right and on_bottom:
            return "br"
        if on_right:
            return "r"
        if on_bottom:
            return "b"
        return None

    def _handle_borderless_resize_event(self, event: pygame.event.Event) -> bool:
        if not self.settings.borderless_window:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            zone = self._borderless_resize_zone(event.pos)
            if zone is None:
                return False
            sw, sh = self.screen.get_size()
            self._borderless_resize = zone
            self._borderless_resize_anchor = (event.pos[0], event.pos[1], sw, sh)
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._borderless_resize is not None:
                self._borderless_resize = None
                self._borderless_resize_anchor = None
                return True
            return False
        if event.type == pygame.MOUSEMOTION and self._borderless_resize:
            anchor = self._borderless_resize_anchor
            if anchor is None:
                return False
            start_x, start_y, start_w, start_h = anchor
            mx, my = event.pos
            new_w, new_h = start_w, start_h
            if "r" in self._borderless_resize:
                new_w = start_w + (mx - start_x)
            if "b" in self._borderless_resize:
                new_h = start_h + (my - start_y)
            self._set_window_size(new_w, new_h)
            return True
        return False

    def _update_borderless_cursor(self) -> None:
        if not self.settings.borderless_window:
            cursor_key = "arrow"
        else:
            zone = self._borderless_resize or self._borderless_resize_zone(
                pygame.mouse.get_pos()
            )
            cursor_key = zone or "arrow"
        if cursor_key == self._borderless_cursor:
            return
        cursors = {
            "arrow": pygame.SYSTEM_CURSOR_ARROW,
            "r": pygame.SYSTEM_CURSOR_SIZEWE,
            "b": pygame.SYSTEM_CURSOR_SIZENS,
            "br": pygame.SYSTEM_CURSOR_SIZENWSE,
        }
        pygame.mouse.set_system_cursor(cursors[cursor_key])
        self._borderless_cursor = cursor_key

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
                elif self._handle_borderless_resize_event(event):
                    pass
                else:
                    self.handle_event(event)

            self.update(dt)
            self.draw()
            self._update_borderless_cursor()
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
                self._set_ui(UiState.PLAYING)
            elif event.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _playing_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._set_ui(UiState.PAUSED)
            self.pause_selection = 0
            self.audio.play("ui")
            return
        action = self.bindings.action_down(event)
        if action == Action.PAUSE:
            self._set_ui(UiState.PAUSED)
            self.pause_selection = 0
            self.audio.play("ui")
        elif action == Action.QUIT:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif action == Action.TOGGLE_AI_ARENA:
            self.state.toggle_ai_arena()
            self._set_ui(UiState.PLAYING)

    def _pause_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.pause_selection = (self.pause_selection - 1) % 4
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.pause_selection = (self.pause_selection + 1) % 4
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._pause_activate()
            elif event.key == pygame.K_ESCAPE:
                self._set_ui(UiState.PLAYING)
            elif event.key == pygame.K_p:
                self._set_ui(UiState.PLAYING)

    def _pause_activate(self) -> None:
        opts = ["resume", "controls", "ai_arena", "quit"]
        choice = opts[self.pause_selection]
        if choice == "resume":
            self._set_ui(UiState.PLAYING)
        elif choice == "controls":
            self._set_ui(UiState.CONTROLS)
            self.rebind_action = None
            self._ctrl_settings_row = None
            self._ctrl_idx = Action.ROTATE_LEFT
        elif choice == "ai_arena":
            self.state.toggle_ai_arena()
            self._set_ui(UiState.PLAYING)
            self.audio.play("ui")
        elif choice == "quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _controls_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._set_ui(UiState.PAUSED)
                return
            if event.key == pygame.K_r:
                self.bindings.restore_defaults()
                self.bindings.save()
                self.audio.play("ui")
                return
            if self.rebind_action is None:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    if self._ctrl_settings_row == "sfx":
                        self.settings.adjust_sfx_volume(-config.VOLUME_STEP)
                        self.audio.sfx_volume = self.settings.sfx_volume
                        self.audio.play("ui")
                    elif self._ctrl_settings_row == "music":
                        self.settings.adjust_music_volume(-config.VOLUME_STEP)
                        self.music.set_volume(self.settings.music_volume)
                        self._sync_music()
                        self.audio.play("ui")
                    elif (
                        self._ctrl_settings_row == "borderless"
                        and self.settings.borderless_window
                    ):
                        self._nudge_window_size(-config.WINDOW_SIZE_STEP, 0)
                        self.audio.play("ui")
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    if self._ctrl_settings_row == "sfx":
                        self.settings.adjust_sfx_volume(config.VOLUME_STEP)
                        self.audio.sfx_volume = self.settings.sfx_volume
                        self.audio.play("ui")
                    elif self._ctrl_settings_row == "music":
                        self.settings.adjust_music_volume(config.VOLUME_STEP)
                        self.music.set_volume(self.settings.music_volume)
                        self._sync_music()
                        self.audio.play("ui")
                    elif (
                        self._ctrl_settings_row == "borderless"
                        and self.settings.borderless_window
                    ):
                        self._nudge_window_size(config.WINDOW_SIZE_STEP, 0)
                        self.audio.play("ui")
                elif event.key in (pygame.K_UP, pygame.K_w):
                    if (
                        self._ctrl_settings_row == "borderless"
                        and self.settings.borderless_window
                    ):
                        self._nudge_window_size(0, config.WINDOW_SIZE_STEP)
                        self.audio.play("ui")
                    else:
                        self._controls_nav_up()
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    if (
                        self._ctrl_settings_row == "borderless"
                        and self.settings.borderless_window
                    ):
                        self._nudge_window_size(0, -config.WINDOW_SIZE_STEP)
                        self.audio.play("ui")
                    else:
                        self._controls_nav_down()
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self._ctrl_settings_row == "work":
                        self.settings.toggle_work_mode()
                        self.audio.play("ui")
                    elif self._ctrl_settings_row == "borderless":
                        self.settings.toggle_borderless()
                        self._apply_display_mode()
                        self.audio.play("ui")
                    elif self._ctrl_settings_row is None:
                        self.rebind_action = self._ctrl_idx
            return
        binding = self.bindings.binding_from_event(event)
        if binding and self.rebind_action:
            err = self.bindings.set_binding(self.rebind_action, binding)
            if err is None:
                self.bindings.save()
                self.audio.play("ui")
            self.rebind_action = None

    def _controls_nav_up(self) -> None:
        if self._ctrl_settings_row is None:
            idx = list(Action).index(self._ctrl_idx)
            if idx == 0:
                self._ctrl_settings_row = SETTINGS_ROWS[-1]
            else:
                self._ctrl_idx = list(Action)[idx - 1]
            return
        row_idx = SETTINGS_ROWS.index(self._ctrl_settings_row)
        if row_idx == 0:
            return
        self._ctrl_settings_row = SETTINGS_ROWS[row_idx - 1]

    def _controls_nav_down(self) -> None:
        if self._ctrl_settings_row is None:
            idx = list(Action).index(self._ctrl_idx)
            if idx < len(Action) - 1:
                self._ctrl_idx = list(Action)[idx + 1]
            return
        row_idx = SETTINGS_ROWS.index(self._ctrl_settings_row)
        if row_idx >= len(SETTINGS_ROWS) - 1:
            self._ctrl_settings_row = None
            self._ctrl_idx = list(Action)[0]
            return
        self._ctrl_settings_row = SETTINGS_ROWS[row_idx + 1]

    def _return_to_menu(self) -> None:
        self._set_ui(UiState.MENU)
        self.state.phase = Phase.MENU
        self._game_over_saved = False

    def _set_ui(self, ui: UiState) -> None:
        self.ui = ui
        self._sync_music()

    def _sync_music(self) -> None:
        if self.ui == UiState.PLAYING:
            if self.settings.music_volume > 0.0 and self.music.has_tracks():
                self.music.unpause()
            else:
                self.music.stop()
        elif self.ui in (UiState.PAUSED, UiState.CONTROLS):
            self.music.pause()
        else:
            self.music.stop()

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
        self.music.tick(dt)
        if self.state.phase == Phase.PLAYING:
            self.audio.play_batch(self.state.pending_sounds)

        if self.state.phase == Phase.GAME_OVER:
            self._set_ui(UiState.GAME_OVER)
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
            self._draw_game_glow()
            self._draw_bloom()
            self._draw_game_entities()
            if not self.settings.work_mode:
                self._draw_game_over()
            else:
                self._draw_game_over_minimal()
        elif self.ui == UiState.PAUSED:
            self._draw_game_glow()
            self._draw_bloom()
            self._draw_game_entities()
            self._draw_pause_menu()
        elif self.ui == UiState.CONTROLS:
            self._draw_controls()
        else:
            self._draw_game_glow()
            self._draw_bloom()
            self._draw_game_entities()
            if not self.settings.work_mode:
                self._draw_hud()

        pygame.display.flip()

    def _draw_arena(self) -> None:
        arena = self.state.arena
        if not arena:
            return
        x, y, aw, ah = (int(v) for v in arena.rect)
        sw, sh = self.screen.get_size()
        drift_t = pygame.time.get_ticks() * 0.001
        amp = config.NEBULA_DRIFT_AMP
        for puff, (nx, ny, drift_rate, phase, stretch_x, stretch_y) in zip(
            self._ensure_nebula_puffs(sw, sh),
            (
                (0.34, 0.4, 1.0, 0.0, 1.08, 0.94),
                (0.66, 0.58, 1.32, 2.3, 0.92, 1.12),
                (0.5, 0.74, 0.86, 4.2, 1.14, 0.88),
            ),
            strict=True,
        ):
            t = drift_t * config.NEBULA_DRIFT_RATE * drift_rate + phase
            cx = int(
                nx * sw
                + math.sin(t) * sw * amp
                + math.sin(t * 1.55 + 0.9) * sw * amp * 0.42
            )
            cy = int(
                ny * sh
                + math.cos(t * 0.78) * sh * amp * 0.9
                + math.cos(t * 1.25 + 0.5) * sh * amp * 0.38
            )
            pulse = 1.0 + 0.06 * math.sin(t * 0.62 + phase)
            pw, ph = puff.get_size()
            draw_w = max(8, int(pw * stretch_x * pulse))
            draw_h = max(8, int(ph * stretch_y / pulse))
            scaled = pygame.transform.smoothscale(puff, (draw_w, draw_h))
            self.screen.blit(scaled, (cx - draw_w // 2, cy - draw_h // 2))
        twinkle_t = drift_t
        for sx, sy, base, phase, speed, amp in arena.stars:
            bright = base
            if amp > 0:
                bright = base + amp * math.sin(twinkle_t * speed + phase)
                bright = max(0.15, min(1.0, bright))
            c = int(80 + 120 * bright)
            self.screen.set_at((int(sx) % sw, int(sy) % sh), (c, c, c))

    def _draw_asteroids(self) -> None:
        arena = self.state.arena
        if not arena:
            return
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

    def _draw_game_glow(self) -> None:
        if self.state.screen_flash > 0 and not self.settings.work_mode:
            flash = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            t = min(
                1.0,
                self.state.screen_flash / config.SCREEN_FLASH_DURATION,
            )
            alpha = int(config.SCREEN_FLASH_ALPHA * t)
            flash.fill((255, 255, 255, alpha))
            self.screen.blit(flash, (0, 0))

        for p in self.state.particles.particles:
            alpha = int(255 * (p.lifetime / p.max_lifetime))
            px, py = int(p.position[0]), int(p.position[1])
            radius = max(1, int(p.size))
            if radius >= 2:
                glow = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
                cx, cy = radius * 2, radius * 2
                pygame.draw.circle(
                    glow,
                    (*p.color[:3], max(0, min(255, alpha // 2))),
                    (cx, cy),
                    radius + 1,
                )
                pygame.draw.circle(
                    glow,
                    (*p.color[:3], max(0, min(255, alpha))),
                    (cx, cy),
                    radius,
                )
                self.screen.blit(glow, (px - cx, py - cy))
            else:
                pygame.draw.circle(self.screen, p.color[:3], (px, py), radius)

        for proj in self.state.projectiles:
            tail = (
                int(proj.position[0] - proj.velocity[0] * 0.05),
                int(proj.position[1] - proj.velocity[1] * 0.05),
            )
            head = (int(proj.position[0]), int(proj.position[1]))
            pygame.draw.line(self.screen, proj.color, tail, head, 3)
            pygame.draw.line(
                self.screen,
                tuple(min(255, c + 40) for c in proj.color),
                (
                    int(proj.position[0] - proj.velocity[0] * 0.02),
                    int(proj.position[1] - proj.velocity[1] * 0.02),
                ),
                head,
                1,
            )

    def _draw_game_entities(self) -> None:
        self._draw_asteroids()
        for pu in self.state.powerups:
            self._draw_powerup(pu)
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
        pulse = 1.0 + 0.06 * math.sin(pu.lifetime * 5.0)
        outer = int(13 * pulse)
        pygame.draw.circle(self.screen, (28, 30, 36), (x, y), outer + 1)
        pygame.draw.circle(self.screen, (52, 54, 60), (x, y), outer)
        pygame.draw.circle(self.screen, col, (x, y), outer, 2)

        if pu.kind == PowerUpKind.SHIELD:
            pts = [
                (x, y - 9), (x + 8, y - 3), (x + 8, y + 5),
                (x, y + 9), (x - 8, y + 5), (x - 8, y - 3),
            ]
            fill = tuple(max(0, int(c * 0.55)) for c in col)
            pygame.draw.polygon(self.screen, fill, pts, 0)
            pygame.draw.polygon(self.screen, (240, 245, 255), pts, 1)
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
        paint = _ship_paint(ship)
        fill = paint["fill"]
        aux_fill = paint["aux_fill"]
        highlight = paint["highlight"]
        outline = paint["outline"]
        canopy = paint["canopy"]
        exhaust = paint["exhaust"]
        nozzle = paint["nozzle"]
        glow_col = paint["glow_col"]
        nose_line = paint["nose_line"]
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
        glow_alpha = 45 if ship.is_boss_evolved else 22
        glow_size = 20 if ship.is_boss_evolved else 14
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
        pygame.draw.polygon(self.screen, paint["rim"], rim_pts, 1)
        for aux in ship.aux_hull_points():
            aux_pts = [(int(p[0]), int(p[1])) for p in aux]
            if len(aux_pts) >= 3:
                pygame.draw.polygon(self.screen, aux_fill, aux_pts, 0)
                pygame.draw.polygon(self.screen, outline, aux_pts, 1)
        pygame.draw.polygon(self.screen, fill, pts, 0)
        inner_pts = _shrink_poly(pts, centroid, 0.70)
        pygame.draw.polygon(self.screen, paint["inner_fill"], inner_pts, 0)
        hi = [(int(p[0]), int(p[1])) for p in ship.highlight_points()]
        if len(hi) >= 3:
            pygame.draw.polygon(self.screen, highlight, hi, 0)
            hi_rim = _shrink_poly(hi, _poly_centroid(hi), 0.88)
            pygame.draw.polygon(self.screen, paint["hi_edge"], hi_rim, 1)
        pygame.draw.polygon(self.screen, outline, pts, 2)
        gleam_pts = [(p[0] - 1, p[1] - 1) for p in pts]
        pygame.draw.polygon(self.screen, paint["gleam"], gleam_pts, 1)
        na, nb = ship.nose_line()
        pygame.draw.line(
            self.screen,
            tuple(max(0, int(c * 0.45)) for c in nose_line),
            (int(na[0]), int(na[1])),
            (int(nb[0]), int(nb[1])),
            3,
        )
        pygame.draw.line(
            self.screen,
            nose_line,
            (int(na[0]), int(na[1])),
            (int(nb[0]), int(nb[1])),
            1,
        )
        panel_col = paint["panel"]
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

    def _vignette_for_size(self, w: int, h: int) -> pygame.Surface:
        if self._vignette_surface is not None and self._vignette_size == (w, h):
            return self._vignette_surface
        sample_w = max(1, w // 4)
        sample_h = max(1, h // 4)
        sample = pygame.Surface((sample_w, sample_h), pygame.SRCALPHA)
        cx, cy = sample_w * 0.5, sample_h * 0.5
        max_r = math.hypot(cx, cy)
        strength = config.VIGNETTE_STRENGTH
        for y in range(sample_h):
            for x in range(sample_w):
                dist = math.hypot(x - cx, y - cy) / max_r
                alpha = int(strength * min(1.0, dist**2.1))
                sample.set_at((x, y), (0, 0, 0, alpha))
        vignette = pygame.transform.smoothscale(sample, (w, h))
        self._vignette_size = (w, h)
        self._vignette_surface = vignette
        return vignette

    def _draw_bloom(self) -> None:
        w, h = self.screen.get_size()
        if w < 8 or h < 8:
            return
        div = max(2, config.BLOOM_SCALE_DIV)
        small = pygame.transform.smoothscale(
            self.screen,
            (max(1, w // div), max(1, h // div)),
        )
        bloomed = pygame.transform.smoothscale(small, (w, h))
        bloomed.set_alpha(config.BLOOM_ALPHA)
        self.screen.blit(bloomed, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        self.screen.blit(self._vignette_for_size(w, h), (0, 0))

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

    def _draw_volume_slider(
        self,
        label: str,
        volume: float,
        y: int,
        selected: bool,
    ) -> None:
        pct = int(volume * 100)
        prefix = "> " if selected else "  "
        color = ACCENT if selected else TEXT
        text = self.font.render(f"{prefix}{label}: {pct}%", True, color)
        self.screen.blit(text, (60, y))
        bar_x, bar_y, bar_w, bar_h = 340, y + 6, 220, 10
        pygame.draw.rect(self.screen, (40, 40, 55), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * volume)
        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (bar_x, bar_y, fill_w, bar_h))

    def _draw_controls(self) -> None:
        self.screen.fill(MENU_BG)
        title = self.font_lg.render("CONTROLS", True, ACCENT)
        self.screen.blit(title, (40, 30))
        hint = self.font_sm.render(
            "Up/Down select — L/R volume — Enter toggle — borderless: drag edges or arrows resize",
            True,
            (140, 140, 150),
        )
        self.screen.blit(hint, (40, 80))
        settings_selected = self._ctrl_settings_row is not None and not self.rebind_action
        self._draw_volume_slider(
            "SFX volume",
            self.settings.sfx_volume,
            118,
            settings_selected and self._ctrl_settings_row == "sfx",
        )
        self._draw_volume_slider(
            "Music volume",
            self.settings.music_volume,
            150,
            settings_selected and self._ctrl_settings_row == "music",
        )
        work_label = "ON" if self.settings.work_mode else "OFF"
        work_color = ACCENT if settings_selected and self._ctrl_settings_row == "work" else TEXT
        work_prefix = "> " if settings_selected and self._ctrl_settings_row == "work" else "  "
        work_surf = self.font.render(f"{work_prefix}Work mode: {work_label}", True, work_color)
        self.screen.blit(work_surf, (60, 182))
        border_label = "ON" if self.settings.borderless_window else "OFF"
        border_color = (
            ACCENT if settings_selected and self._ctrl_settings_row == "borderless" else TEXT
        )
        border_prefix = (
            "> " if settings_selected and self._ctrl_settings_row == "borderless" else "  "
        )
        size_note = ""
        if self.settings.borderless_window:
            w, h = self.screen.get_size()
            size_note = f"  {w}×{h}"
        border_surf = self.font.render(
            f"{border_prefix}Borderless window: {border_label}{size_note}",
            True,
            border_color,
        )
        self.screen.blit(border_surf, (60, 214))
        if not self.music.has_tracks():
            note = self.font_sm.render(
                f"No tracks in {config.MUSIC_DIR}/ — add .mp3 files to enable music",
                True,
                (120, 120, 130),
            )
            self.screen.blit(note, (60, 244))
        if self.rebind_action:
            msg = self.font.render(
                f"Press key, mouse button, or wheel for {ACTION_LABELS[self.rebind_action]}...",
                True,
                (255, 220, 100),
            )
            self.screen.blit(msg, (40, 268))
        idx = self._ctrl_idx
        binding_y = 276
        for i, action in enumerate(Action):
            b = self.bindings.bindings[action]
            color = ACCENT if action == idx and not self.rebind_action else TEXT
            prefix = "> " if action == idx and not self.rebind_action else "  "
            line = f"{prefix}{ACTION_LABELS[action]}: {b.label}"
            surf = self.font.render(line, True, color)
            self.screen.blit(surf, (60, binding_y + i * 32))

    def _draw_game_over_minimal(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        title = self.font_lg.render("GAME OVER", True, (255, 80, 60))
        self.screen.blit(title, title.get_rect(center=(self.screen.get_width() // 2, 280)))
        prompt = self.font.render("Enter / Esc: menu", True, (140, 140, 150))
        self.screen.blit(prompt, prompt.get_rect(center=(self.screen.get_width() // 2, 340)))

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