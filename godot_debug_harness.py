"""Minimal Godot draw harness for MazeCanvas.

This harness intentionally bypasses the full GUI stack and does one thing:
  1) Build a real GameEngine instance
  2) Pull `engine.view().maze_snapshot`
  3) Feed that snapshot directly into `MazeCanvas`

Use this to isolate whether Godot is rendering any maze geometry at all.
"""

from __future__ import annotations

import argparse
from collections import deque
import logging
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from db import HACKER_SEED_QUESTIONS, open_repo
from gui.maze_canvas import MazeCanvas
from main import (
    Command,
    GameEngine,
    StartupConfig,
    _build_maze,
    _initialize_question_bank,
    _utc_now_iso,
)
from maze import Direction, Position
from puzzles import PuzzleRegistry


log = logging.getLogger("godot_debug_harness")


def _gate_ids_from_maze(maze: object) -> list[str]:
    raw = {
        getattr(cell, "puzzle_id", None)
        for cell in getattr(maze, "cells").values()
    }
    return sorted(gate_id for gate_id in raw if gate_id is not None)


def _shortest_path_dirs(maze: object, start: Position, target: Position) -> list[str]:
    """Return direction tokens from start -> target using BFS."""
    if start == target:
        return []

    q: deque[Position] = deque([start])
    parent: dict[Position, tuple[Position, str] | None] = {start: None}
    while q:
        cur = q.popleft()
        if cur == target:
            break
        for direction in sorted(getattr(maze, "available_moves")(cur), key=lambda d: d.name):
            nxt = getattr(maze, "next_pos")(cur, direction)
            if nxt is None or nxt in parent:
                continue
            parent[nxt] = (cur, direction.name)
            q.append(nxt)

    if target not in parent:
        return []

    rev: list[str] = []
    cur = target
    while cur != start:
        prev, direction = parent[cur]  # type: ignore[index]
        rev.append(direction)
        cur = prev
    rev.reverse()
    return rev


def _reachable_positions(maze: object) -> list[Position]:
    """Enumerate positions reachable from maze.start in row/col order."""
    start: Position = getattr(maze, "start")
    q: deque[Position] = deque([start])
    seen: set[Position] = {start}
    out: list[Position] = []
    while q:
        cur = q.popleft()
        out.append(cur)
        for direction in sorted(getattr(maze, "available_moves")(cur), key=lambda d: d.name):
            nxt = getattr(maze, "next_pos")(cur, direction)
            if nxt is None or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    out.sort(key=lambda p: (p.row, p.col))
    return out


def _build_sweep_actions(maze: object) -> list[tuple[str, str]]:
    """Build deterministic action list: traverse all cells, show N/E/S/W at each."""
    actions: list[tuple[str, str]] = []
    current: Position = getattr(maze, "start")
    for target in _reachable_positions(maze):
        for direction in _shortest_path_dirs(maze, current, target):
            actions.append(("move", direction))
            current = getattr(maze, "next_pos")(current, Direction[direction])
        for face in ("N", "E", "S", "W"):
            actions.append(("face", face))
    return actions


def _build_engine(
    *,
    size: int,
    seed: int,
    gates: int,
    reveal_all: bool,
) -> tuple[GameEngine, TemporaryDirectory]:
    tmpdir = TemporaryDirectory(prefix="godot-harness-")
    save_path = Path(tmpdir.name) / "harness_save.db"
    repo = open_repo(save_path)
    _initialize_question_bank(repo, HACKER_SEED_QUESTIONS, reset_game=True)

    config = StartupConfig(
        reset_game=True,
        maze_size=size,
        maze_seed=seed,
        num_gates=gates,
        gui=True,
        use_godot=True,
    )
    maze = _build_maze(config)
    puzzles = PuzzleRegistry()

    player = repo.get_or_create_player("debug_harness")
    player_id = player["id"] if isinstance(player, dict) else player.id

    if reveal_all:
        visited = [
            {"row": r, "col": c}
            for r in range(maze.height)
            for c in range(maze.width)
        ]
    else:
        visited = [{"row": maze.start.row, "col": maze.start.col}]

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        # Solve gates in harness so movement buttons can test redraw freely.
        "solved_gates": _gate_ids_from_maze(maze),
        "started_at": _utc_now_iso(),
        "visited": visited,
        "hints_used": 0,
        "maze_size": size,
        "num_gates": gates,
        "maze_seed": seed,
    }

    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = GameEngine(
        maze=maze,
        repo=repo,
        puzzles=puzzles,
        player_id=player_id,
        game_id=game_id,
    )
    return engine, tmpdir


class HarnessWindow(QWidget):
    def __init__(
        self,
        *,
        engine: GameEngine,
        use_godot: bool,
        sweep_angles: bool = False,
        sweep_step_ms: int = 250,
        auto_quit_on_sweep_done: bool = False,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._last_engine_messages: list[str] = []
        self._last_view = None
        self._sweep_enabled = sweep_angles
        self._sweep_step_ms = max(50, sweep_step_ms)
        self._auto_quit_on_sweep_done = auto_quit_on_sweep_done
        self._sweep_actions: list[tuple[str, str]] = []
        self._sweep_idx = 0
        self._sweep_done = False
        self._sweep_errors: list[str] = []
        self._seen_error_lines: set[str] = set()
        self._sweep_timer: QTimer | None = None

        self.setWindowTitle("Godot Debug Harness — Engine View -> MazeCanvas")
        self.resize(1000, 750)

        root = QVBoxLayout(self)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-family: monospace;")
        root.addWidget(self._status)

        controls = QGridLayout()
        root.addLayout(controls)

        refresh_btn = QPushButton("Refresh From engine.view()")
        refresh_btn.clicked.connect(self.refresh_from_engine_view)
        controls.addWidget(refresh_btn, 0, 0, 1, 2)

        for idx, direction in enumerate(("N", "S", "E", "W")):
            btn = QPushButton(f"Move {direction}")
            btn.clicked.connect(lambda _checked=False, d=direction: self.move(d))
            controls.addWidget(btn, 1 + idx // 2, idx % 2)

        self._canvas = MazeCanvas(use_godot=use_godot)
        # Route Godot WASD direction events back into the engine path.
        self._canvas.direction_clicked.connect(self.move)
        root.addWidget(self._canvas, 1)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_text)
        self._status_timer.start(400)

        self.refresh_from_engine_view()

        if self._sweep_enabled:
            self._start_sweep()

    def _apply_view(self, view: object) -> None:
        self._last_view = view
        snapshot = getattr(view, "maze_snapshot", None)
        if snapshot is None:
            self._status.setText("No maze_snapshot on GameView.")
            return
        self._canvas.update_maze(snapshot)
        pos = getattr(view, "pos", {"row": 0, "col": 0})
        self._canvas.highlight_player((pos["row"], pos["col"]))
        self._update_status_text()

    def _update_status_text(self) -> None:
        proc = self._canvas._godot_process
        proc_state = proc.state().name if proc is not None else "NotStarted"
        ws_connected = self._canvas._ws_client is not None

        if self._last_view is None:
            view_line = "view: <none>"
        else:
            pos = self._last_view.pos
            view_line = (
                f"view: pos=({pos['row']},{pos['col']}) "
                f"moves={self._last_view.move_count} "
                f"visited={self._last_view.visited_count}"
            )

        lines = [
            f"godot_available={self._canvas._godot_available}",
            f"fallback_reason={self._canvas._fallback_reason or 'None'}",
            f"ws_port={self._canvas._ws_port or 0} ws_connected={ws_connected}",
            f"godot_process_state={proc_state}",
            self._sweep_status_line(),
            view_line,
            "last_engine_messages="
            + (" | ".join(self._last_engine_messages) if self._last_engine_messages else "<none>"),
        ]
        self._status.setText("\n".join(lines))

    def refresh_from_engine_view(self) -> None:
        view = self._engine.view()
        self._last_engine_messages = ["engine.view()"]
        self._apply_view(view)

    def move(self, direction: str) -> None:
        out = self._engine.handle(Command(verb="go", args=[direction]))
        self._last_engine_messages = out.messages
        self._apply_view(out.view)

    def _sweep_status_line(self) -> str:
        if not self._sweep_enabled:
            return "sweep=disabled"
        total = len(self._sweep_actions)
        status = "done" if self._sweep_done else "running"
        return f"sweep={status} step={self._sweep_idx}/{total} errors={len(self._sweep_errors)}"

    def _start_sweep(self) -> None:
        self._sweep_actions = _build_sweep_actions(self._engine.maze)
        self._sweep_idx = 0
        self._sweep_done = False
        self._sweep_errors.clear()
        self._seen_error_lines.clear()
        self._sweep_timer = QTimer(self)
        self._sweep_timer.timeout.connect(self._run_sweep_step)
        self._sweep_timer.start(self._sweep_step_ms)
        log.info("Starting angle sweep: %d actions", len(self._sweep_actions))

    def _record_sweep_error(self, msg: str) -> None:
        if msg in self._sweep_errors:
            return
        self._sweep_errors.append(msg)
        log.error("Sweep error: %s", msg)
        if self._sweep_timer and self._sweep_timer.isActive():
            self._sweep_timer.stop()

    def _detect_runtime_errors(self) -> None:
        if self._canvas._fallback_reason:
            self._record_sweep_error(f"Fallback triggered: {self._canvas._fallback_reason}")

        if self._canvas._godot_available:
            proc = self._canvas._godot_process
            if proc is None or proc.state().name == "NotRunning":
                self._record_sweep_error("Godot process is not running during sweep")

        for line in self._canvas._godot_stderr_tail:
            up = line.upper()
            if any(token in up for token in ("SCRIPT ERROR", "SHADER ERROR", "ERROR:")):
                if line not in self._seen_error_lines:
                    self._seen_error_lines.add(line)
                    self._record_sweep_error(f"Godot stderr: {line}")

    def _finish_sweep(self) -> None:
        self._sweep_done = True
        if self._sweep_timer and self._sweep_timer.isActive():
            self._sweep_timer.stop()

        if self._sweep_errors:
            summary = (
                f"SWEEP FAIL: {len(self._sweep_errors)} error(s) over "
                f"{len(self._sweep_actions)} actions"
            )
            print(summary)
            for err in self._sweep_errors:
                print(f" - {err}")
            self._last_engine_messages = [summary]
        else:
            summary = f"SWEEP PASS: {len(self._sweep_actions)} actions, no Godot errors detected"
            print(summary)
            log.info(summary)
            self._last_engine_messages = [summary]

        self._update_status_text()

        if self._auto_quit_on_sweep_done:
            app = QApplication.instance()
            if app is not None:
                def _shutdown() -> None:
                    self.shutdown_and_quit(app, quit_delay_ms=150)

                QTimer.singleShot(300, _shutdown)

    def _run_sweep_step(self) -> None:
        if self._sweep_done:
            return

        self._detect_runtime_errors()
        if self._sweep_errors:
            self._finish_sweep()
            return

        if self._sweep_idx >= len(self._sweep_actions):
            self._finish_sweep()
            return

        action, payload = self._sweep_actions[self._sweep_idx]
        self._sweep_idx += 1

        if action == "move":
            out = self._engine.handle(Command(verb="go", args=[payload]))
            self._last_engine_messages = out.messages or [f"move {payload}"]
            self._apply_view(out.view)
            for msg in out.messages:
                if msg in {"Blocked path.", "Invalid direction.", "Unknown command.", "No pending puzzle."}:
                    self._record_sweep_error(f"Engine move error at step {self._sweep_idx}: {msg}")
                    break
        elif action == "face":
            self._canvas.set_view_direction(payload)
            self._last_engine_messages = [f"face {payload}"]

        self._detect_runtime_errors()
        if self._sweep_errors:
            self._finish_sweep()

    def shutdown_and_quit(self, app: QApplication, *, quit_delay_ms: int = 150) -> None:
        """Terminate Godot cleanly before quitting the Qt app."""
        try:
            self._canvas._is_closing = True
            self._canvas._kill_godot()
        except Exception:
            pass
        self.close()
        QTimer.singleShot(quit_delay_ms, app.quit)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Engine view -> MazeCanvas Godot debug harness")
    parser.add_argument("--size", type=int, default=5, help="Maze size (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Maze seed (default: 42)")
    parser.add_argument("--gates", type=int, default=2, help="Number of gates (default: 2)")
    parser.add_argument(
        "--no-godot",
        action="store_true",
        help="Disable Godot and force 2D fallback in MazeCanvas",
    )
    parser.add_argument(
        "--hide-unvisited",
        action="store_true",
        help="Use engine's normal fog of war (default is reveal-all for visibility)",
    )
    parser.add_argument(
        "--sweep-angles",
        action="store_true",
        help="Traverse reachable cells and display N/E/S/W at each position",
    )
    parser.add_argument(
        "--sweep-step-ms",
        type=int,
        default=200,
        help="Step interval for --sweep-angles actions (default: 200ms)",
    )
    parser.add_argument(
        "--auto-quit-on-sweep-done",
        action="store_true",
        help="Close the harness automatically once sweep completes",
    )
    parser.add_argument(
        "--auto-quit-seconds",
        type=float,
        default=0.0,
        help="Auto-close harness after N seconds (useful for quick smoke runs)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python-side logging level",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine, tempdir = _build_engine(
        size=args.size,
        seed=args.seed,
        gates=args.gates,
        reveal_all=not args.hide_unvisited,
    )
    log.info(
        "Built harness engine with size=%d seed=%d gates=%d",
        args.size,
        args.seed,
        args.gates,
    )

    app = QApplication.instance() or QApplication(sys.argv)
    window = HarnessWindow(
        engine=engine,
        use_godot=not args.no_godot,
        sweep_angles=args.sweep_angles,
        sweep_step_ms=args.sweep_step_ms,
        auto_quit_on_sweep_done=args.auto_quit_on_sweep_done,
    )
    app.aboutToQuit.connect(window.close)
    window.show()

    if args.auto_quit_seconds > 0:
        def _shutdown() -> None:
            window.shutdown_and_quit(app, quit_delay_ms=200)

        QTimer.singleShot(int(args.auto_quit_seconds * 1000), _shutdown)

    exit_code = app.exec()
    tempdir.cleanup()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
