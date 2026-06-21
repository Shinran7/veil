"""Headless bout recording and AI behavior analysis."""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TextIO

from arena import Arena
from game import GameMode, GameState, Phase
from ship import Ship
from utils import vec_len, wrapped_distance


TELEMETRY_AI_REVISION = "2026-06-20-dogfight-19"

VARIANT_ORDER = ("light", "balanced", "heavy")
VARIANT_LABELS = {
    "light": "Light",
    "balanced": "Medium",
    "heavy": "Heavy",
}


@dataclass
class TelemetrySession:
    started_at: float
    seed: int | None
    ai_revision: str
    bout_target: int
    arena_size: tuple[int, int]
    frames_path: str
    events_path: str
    bouts_completed: int = 0
    frames_written: int = 0
    events_written: int = 0
    streak_histogram: dict[int, int] = field(default_factory=dict)
    completed_fully: bool = False
    stop_reason: str = ""


@dataclass
class AnalysisReport:
    sessions: int = 0
    frames: int = 0
    deaths: int = 0
    deaths_by_mode: dict[str, int] = field(default_factory=dict)
    missed_tail_shots: int = 0
    flee_while_behind: int = 0
    orbit_no_fire: int = 0
    max_champion_streak: int = 0
    champion_streak_histogram: dict[int, int] = field(default_factory=dict)
    variant_bout_wins: dict[str, int] = field(default_factory=dict)
    variant_deaths: dict[str, int] = field(default_factory=dict)
    variant_max_streak: dict[str, int] = field(default_factory=dict)


class TelemetryRecorder:
    """Writes compact JSONL frame + event streams for AI arena bouts."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.frames_path = run_dir / "frames.jsonl"
        self.events_path = run_dir / "events.jsonl"
        self.session_path = run_dir / "session.json"
        self._frames_file: TextIO | None = None
        self._events_file: TextIO | None = None
        self.session: TelemetrySession | None = None
        self._tick = 0
        self._alive_before: dict[int, bool] = {}

    def begin(
        self,
        bout_target: int,
        seed: int | None,
        arena_size: tuple[int, int],
    ) -> None:
        self._frames_file = self.frames_path.open("w", encoding="utf-8")
        self._events_file = self.events_path.open("w", encoding="utf-8")
        self.session = TelemetrySession(
            started_at=time.time(),
            seed=seed,
            ai_revision=TELEMETRY_AI_REVISION,
            bout_target=bout_target,
            arena_size=arena_size,
            frames_path=str(self.frames_path),
            events_path=str(self.events_path),
        )
        self._tick = 0

    def close(self) -> TelemetrySession | None:
        if self.session:
            self.session_path.write_text(
                json.dumps(asdict(self.session), indent=2), encoding="utf-8"
            )
        if self._frames_file:
            self._frames_file.close()
            self._frames_file = None
        if self._events_file:
            self._events_file.close()
            self._events_file = None
        return self.session

    def _write_frame(self, row: dict[str, Any]) -> None:
        if not self._frames_file:
            return
        self._frames_file.write(json.dumps(row, separators=(",", ":")) + "\n")
        if self.session:
            self.session.frames_written += 1

    def _write_event(self, row: dict[str, Any]) -> None:
        if not self._events_file:
            return
        self._events_file.write(json.dumps(row, separators=(",", ":")) + "\n")
        if self.session:
            self.session.events_written += 1

    def capture_pre_update(self, state: GameState) -> None:
        if state.mode != GameMode.AI_ARENA:
            return
        self._alive_before = {
            s.ship_id: s.alive for s in state.all_ships if s.ai_controlled
        }

    def capture_post_update(self, state: GameState) -> None:
        if state.mode != GameMode.AI_ARENA or state.arena is None:
            return
        rect = state.arena.rect
        bout = state.ai_bout_number
        for ship in state.all_ships:
            if not ship.ai_controlled:
                continue
            ctrl = state.ai_controllers.get(ship.ship_id)
            ctx = ctrl.last_context if ctrl else None
            row: dict[str, Any] = {
                "t": self._tick,
                "b": bout,
                "id": ship.ship_id,
                "v": ship.variant.value,
                "cw": ship.champion_wins,
                "x": round(ship.position[0], 1),
                "y": round(ship.position[1], 1),
                "vx": round(ship.velocity[0], 1),
                "vy": round(ship.velocity[1], 1),
                "h": round(ship.health / ship.max_health, 3),
                "alive": ship.alive,
            }
            if ctx:
                row.update(
                    {
                        "m": ctx.mode,
                        "tid": ctx.target_id,
                        "td": round(ctx.target_dist, 1),
                        "c": round(ctx.caution, 3),
                        "bh": int(ctx.behind_target),
                        "tg": int(ctx.tail_gunner),
                        "f": int(ctx.fired),
                        "rot": ctx.rotate,
                        "thr": round(ctx.thrust, 3),
                    }
                )
                if ctx.target_id is not None:
                    target = next(
                        (s for s in state.all_ships if s.ship_id == ctx.target_id),
                        None,
                    )
                    if target and ship.alive:
                        raw = vec_len(
                            (
                                target.position[0] - ship.position[0],
                                target.position[1] - ship.position[1],
                            )
                        )
                        wrapped = wrapped_distance(
                            ship.position, target.position, rect
                        )
                        row["td_raw"] = round(raw, 1)
                        row["td_wrap"] = round(wrapped, 1)
            self._write_frame(row)

            was_alive = self._alive_before.get(ship.ship_id, ship.alive)
            if was_alive and not ship.alive:
                self._write_event(
                    {
                        "t": self._tick,
                        "b": bout,
                        "type": "death",
                        "id": ship.ship_id,
                        "v": ship.variant.value,
                        "cw": ship.champion_wins,
                        "m": ctx.mode if ctx else "unknown",
                        "bh": int(ctx.behind_target) if ctx else 0,
                        "c": round(ctx.caution, 3) if ctx else 0.0,
                        "td": round(ctx.target_dist, 1) if ctx else 0.0,
                    }
                )

        self._tick += 1

    def record_bout_end(self, state: GameState, winner: Ship | None) -> None:
        if winner is None:
            return
        self._write_event(
            {
                "t": self._tick,
                "b": state.ai_bout_number,
                "type": "bout_end",
                "winner_id": winner.ship_id,
                "winner_v": winner.variant.value,
                "winner_wins": winner.champion_wins,
            }
        )
        if self.session:
            self.session.bouts_completed += 1
            streak = winner.champion_wins
            self.session.streak_histogram[streak] = (
                self.session.streak_histogram.get(streak, 0) + 1
            )


def simulate_ai_bouts(
    bout_count: int = 20,
    seed: int | None = None,
    output_dir: Path | None = None,
    width: int = 1280,
    height: int = 768,
    max_ticks: int | None = None,
) -> Path:
    """Run headless AI arena bouts and write telemetry to disk."""
    if seed is not None:
        random.seed(seed)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = output_dir or Path("telemetry") / "runs"
    run_dir = base / f"session-{stamp}"
    recorder = TelemetryRecorder(run_dir)
    recorder.begin(bout_count, seed, (width, height))
    tick_budget = max_ticks if max_ticks is not None else bout_count * 15_000

    state = GameState()
    state.arena = Arena.from_window(width, height)
    state.start_ai_arena()
    dt = 1.0 / 60.0
    ticks = 0
    last_bout = state.ai_bout_number

    stop_reason = "completed"
    while recorder.session and recorder.session.bouts_completed < bout_count:
        if ticks >= tick_budget:
            stop_reason = "tick_budget"
            break
        recorder.capture_pre_update(state)
        state.update(dt, {})
        recorder.capture_post_update(state)

        if state.ai_bout_number > last_bout:
            living = state.living_ships()
            recorder.record_bout_end(state, living[0] if living else None)
            last_bout = state.ai_bout_number

        if (
            state.phase == Phase.PLAYING
            and not state.living_ships()
            and state.ai_restart_timer <= 0
        ):
            stop_reason = "no_living_ships"
            break
        ticks += 1

    if recorder.session:
        recorder.session.completed_fully = (
            recorder.session.bouts_completed >= bout_count
        )
        recorder.session.stop_reason = stop_reason
    recorder.close()
    return run_dir


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def analyze_run(run_dir: Path) -> AnalysisReport:
    """Scan one recorded session and tally mistake patterns."""
    report = AnalysisReport(sessions=1)
    frames_path = run_dir / "frames.jsonl"
    events_path = run_dir / "events.jsonl"

    for row in _iter_jsonl(frames_path):
        report.frames += 1
        if not row.get("alive", True):
            continue
        mode = row.get("m", "")
        behind = row.get("bh", 0) == 1
        health = row.get("h", 1.0)
        fired = row.get("f", 0) == 1
        dist = row.get("td", 999.0)

        if (
            behind
            and not fired
            and health < 0.45
            and dist < 420
            and mode in ("panic", "kite", "fight")
        ):
            report.missed_tail_shots += 1
        if behind and mode in ("panic", "kite"):
            report.flee_while_behind += 1
        if mode == "orbit_break" and not fired and dist < 400:
            report.orbit_no_fire += 1

    for row in _iter_jsonl(events_path):
        if row.get("type") == "death":
            report.deaths += 1
            mode = row.get("m", "unknown")
            report.deaths_by_mode[mode] = report.deaths_by_mode.get(mode, 0) + 1
            variant = row.get("v", "unknown")
            report.variant_deaths[variant] = report.variant_deaths.get(variant, 0) + 1
        elif row.get("type") == "bout_end":
            streak = int(row.get("winner_wins", 0))
            report.max_champion_streak = max(report.max_champion_streak, streak)
            report.champion_streak_histogram[streak] = (
                report.champion_streak_histogram.get(streak, 0) + 1
            )
            variant = row.get("winner_v", "unknown")
            report.variant_bout_wins[variant] = (
                report.variant_bout_wins.get(variant, 0) + 1
            )
            report.variant_max_streak[variant] = max(
                report.variant_max_streak.get(variant, 0), streak
            )

    return report


def analyze_directory(root: Path) -> AnalysisReport:
    """Aggregate all session folders under root."""
    combined = AnalysisReport()
    if (root / "frames.jsonl").exists():
        return analyze_run(root)

    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        if not (run_dir / "frames.jsonl").exists():
            continue
        one = analyze_run(run_dir)
        combined.sessions += one.sessions
        combined.frames += one.frames
        combined.deaths += one.deaths
        combined.missed_tail_shots += one.missed_tail_shots
        combined.flee_while_behind += one.flee_while_behind
        combined.orbit_no_fire += one.orbit_no_fire
        combined.max_champion_streak = max(
            combined.max_champion_streak, one.max_champion_streak
        )
        for mode, count in one.deaths_by_mode.items():
            combined.deaths_by_mode[mode] = (
                combined.deaths_by_mode.get(mode, 0) + count
            )
        for streak, count in one.champion_streak_histogram.items():
            combined.champion_streak_histogram[streak] = (
                combined.champion_streak_histogram.get(streak, 0) + count
            )
        for variant, count in one.variant_bout_wins.items():
            combined.variant_bout_wins[variant] = (
                combined.variant_bout_wins.get(variant, 0) + count
            )
        for variant, count in one.variant_deaths.items():
            combined.variant_deaths[variant] = (
                combined.variant_deaths.get(variant, 0) + count
            )
        for variant, streak in one.variant_max_streak.items():
            combined.variant_max_streak[variant] = max(
                combined.variant_max_streak.get(variant, 0), streak
            )
    return combined


def _variant_display_name(variant: str) -> str:
    return VARIANT_LABELS.get(variant, variant)


def _format_variant_balance(report: AnalysisReport) -> list[str]:
    total_wins = sum(report.variant_bout_wins.values())
    total_deaths = sum(report.variant_deaths.values())
    if total_wins == 0 and total_deaths == 0:
        return ["  (no variant data — re-record with current telemetry)"]

    lines: list[str] = []
    all_variants = set(report.variant_bout_wins) | set(report.variant_deaths)
    ordered = [v for v in VARIANT_ORDER if v in all_variants]
    extras = sorted(all_variants - set(VARIANT_ORDER))
    for variant in ordered + extras:
        label = _variant_display_name(variant)
        wins = report.variant_bout_wins.get(variant, 0)
        deaths = report.variant_deaths.get(variant, 0)
        win_pct = 100.0 * wins / max(total_wins, 1)
        death_pct = 100.0 * deaths / max(total_deaths, 1)
        edge = win_pct - death_pct
        streak = report.variant_max_streak.get(variant, 0)
        edge_word = "even"
        if edge >= 8:
            edge_word = "advantage"
        elif edge <= -8:
            edge_word = "disadvantage"
        lines.append(
            f"  {label}: {wins} bout wins ({win_pct:.0f}%)  |  "
            f"{deaths} deaths ({death_pct:.0f}%)  |  "
            f"best streak {streak}  |  {edge_word} ({edge:+.0f} pts)"
        )

    if total_wins > 0:
        best = max(
            (v for v in report.variant_bout_wins if v in VARIANT_ORDER),
            key=lambda v: report.variant_bout_wins.get(v, 0),
            default=None,
        )
        if best:
            lines.append(
                f"  Strongest bout winner: {_variant_display_name(best)}"
            )
    return lines


def format_report(report: AnalysisReport, run_label: str = "") -> str:
    """Plain-English summary for terminal output."""
    lines = ["Veil AI telemetry report"]
    if run_label:
        lines.append(f"Source: {run_label}")
    lines.append(
        f"Sessions: {report.sessions}  |  Frames: {report.frames:,}  |  Deaths: {report.deaths}"
    )
    lines.append("(Normalize frame-tick counts by frames when comparing short vs long runs.)")
    lines.append(f"Longest champion streak seen: {report.max_champion_streak}")
    lines.append("")
    lines.append("Ship variant balance (bout wins vs deaths):")
    lines.extend(_format_variant_balance(report))
    lines.append("")
    lines.append("Deaths by AI mode (top 5):")
    top_modes = sorted(
        report.deaths_by_mode.items(), key=lambda item: item[1], reverse=True
    )[:5]
    if top_modes:
        for mode, count in top_modes:
            pct = 100.0 * count / max(report.deaths, 1)
            lines.append(f"  {mode}: {count} ({pct:.0f}%)")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("Likely improvement opportunities (counts are frame-ticks):")
    lines.append(
        f"  Missed tail shots (hurt, behind, in range, did not fire): {report.missed_tail_shots}"
    )
    lines.append(f"  Fleeing while behind opponent: {report.flee_while_behind}")
    lines.append(f"  Orbit break without firing in range: {report.orbit_no_fire}")

    if report.champion_streak_histogram:
        lines.append("")
        lines.append("Bout wins at end of round:")
        for streak in sorted(report.champion_streak_histogram):
            count = report.champion_streak_histogram[streak]
            lines.append(f"  {streak} win(s): {count} bouts")

    return "\n".join(lines)