"""Pygame debug harness for MazeCanvas with raycaster renderer.

Parallel to ``panda3d_debug_harness.py`` but uses the Pygame backend.

  1) Build a real ``GameEngine`` instance
  2) Pull ``engine.view().maze_snapshot``
  3) Feed that snapshot into ``MazeCanvas`` backed by ``PygameBackend``
  4) Optional automated angle sweep across all reachable positions

Usage:
    python pygame_debug_harness.py [--size 5] [--seed 42] [--sweep-angles]
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from db import HACKER_SEED_QUESTIONS, open_repo
from gui.maze_canvas import MazeCanvas
from gui.renderers.pygame_backend import PygameBackend, PygameViewport
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

log = logging.getLogger("pygame_debug_harness")


# ---------------------------------------------------------------------------
# Maze helpers (identical to panda3d_debug_harness)
# ---------------------------------------------------------------------------

def _gate_ids_from_maze(maze: object) -> list[str]:
    raw = {
        getattr(cell, "puzzle_id", None)
        for cell in getattr(maze, "cells").values()
    }
    return sorted(gid for gid in raw if gid is not None)


def _shortest_path_dirs(maze: object, start: Position, target: Position) -> list[str]:
    if start == target:
        return []
    q: deque[Position] = deque([start])
    parent: dict[Position, tuple[Position, str] | None] = {start: None}
    while q:
        cur = q.popleft()
        if cur == target:
            break
        for d in sorted(getattr(maze, "available_moves")(cur), key=lambda x: x.name):
            nxt = getattr(maze, "next_pos")(cur, d)
            if nxt is None or nxt in parent:
                continue
            parent[nxt] = (cur, d.name)
            q.append(nxt)
    if target not in parent:
        return []
    rev: list[str] = []
    cur = target
    while cur != start:
        prev, d = parent[cur]  # type: ignore[index]
        rev.append(d)
        cur = prev
    rev.reverse()
    return rev


def _reachable_positions(maze: object) -> list[Position]:
    start: Position = getattr(maze, "start")
    q: deque[Position] = deque([start])
    seen: set[Position] = {start}
    out: list[Position] = []
    while q:
        cur = q.popleft()
        out.append(cur)
        for d in sorted(getattr(maze, "available_moves")(cur), key=lambda x: x.name):
            nxt = getattr(maze, "next_pos")(cur, d)
            if nxt is None or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    out.sort(key=lambda p: (p.row, p.col))
    return out


def _build_sweep_actions(maze: object) -> list[tuple[str, str]]:
    actions: list[tuple[str, str]] = []
    current: Position = getattr(maze, "start")
    for target in _reachable_positions(maze):
        for d in _shortest_path_dirs(maze, current, target):
            actions.append(("move", d))
            current = getattr(maze, "next_pos")(current, Direction[d])
        for face in ("N", "E", "S", "W"):
            actions.append(("face", face))
    return actions


# ---------------------------------------------------------------------------
# Engine builder
# ---------------------------------------------------------------------------

def _build_engine(
    *, size: int, seed: int, gates: int, reveal_all: bool,
) -> tuple[GameEngine, TemporaryDirectory]:
    tmpdir = TemporaryDirectory(prefix="pygame-harness-")
    save_path = Path(tmpdir.name) / "harness_save.db"
    repo = open_repo(save_path)
    _initialize_question_bank(repo, HACKER_SEED_QUESTIONS, reset_game=True)

    config = StartupConfig(
        reset_game=True, maze_size=size, maze_seed=seed,
        num_gates=gates, gui=True, use_godot=False,
    )
    maze = _build_maze(config)
    puzzles = PuzzleRegistry()

    player = repo.get_or_create_player("debug_harness")
    pid = player["id"] if isinstance(player, dict) else player.id

    if reveal_all:
        visited = [{"row": r, "col": c}
                   for r in range(maze.height) for c in range(maze.width)]
    else:
        visited = [{"row": maze.start.row, "col": maze.start.col}]

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": _gate_ids_from_maze(maze),
        "started_at": _utc_now_iso(),
        "visited": visited,
        "hints_used": 0,
        "maze_size": size,
        "num_gates": gates,
        "maze_seed": seed,
    }

    game = repo.create_game(
        player_id=pid, maze_id=maze.maze_id,
        maze_version=maze.maze_version, initial_state=initial_state,
    )
    gid = game["id"] if isinstance(game, dict) else game.id

    engine = GameEngine(
        maze=maze, repo=repo, puzzles=puzzles,
        player_id=pid, game_id=gid,
    )
    return engine, tmpdir


# ---------------------------------------------------------------------------
# Harness window
# ---------------------------------------------------------------------------

class HarnessWindow(QWidget):
    def __init__(
        self,
        *,
        engine: GameEngine,
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
        self._sweep_timer: QTimer | None = None

        self.setWindowTitle("Pygame Debug Harness")
        self.resize(1100, 750)

        root = QHBoxLayout(self)

        # -- Left panel: viewport + 2D minimap --------------------------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._facing_label = QLabel("Facing: S")
        self._facing_label.setStyleSheet(
            "font-family: monospace; font-size: 14px; color: #9be79b;",
        )
        left_layout.addWidget(self._facing_label)

        self._backend = PygameBackend()
        self._viewport = PygameViewport(self._backend)
        self._viewport.setMinimumSize(500, 400)
        self._viewport.setStyleSheet("background-color: #000;")

        self._canvas = MazeCanvas(use_godot=False, backend=self._backend)
        self._canvas.direction_clicked.connect(self.move)
        self._canvas.facing_changed.connect(self._on_facing_changed)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._viewport)
        splitter.addWidget(self._canvas)
        splitter.setSizes([400, 250])
        left_layout.addWidget(splitter)
        root.addWidget(left, stretch=3)

        # -- Right panel: status + controls -----------------------------------
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-family: monospace; font-size: 11px;")
        right_layout.addWidget(self._status)

        controls = QGridLayout()
        right_layout.addLayout(controls)

        refresh_btn = QPushButton("Refresh from engine.view()")
        refresh_btn.clicked.connect(self.refresh_from_engine_view)
        controls.addWidget(refresh_btn, 0, 0, 1, 2)

        for idx, d in enumerate(("N", "S", "E", "W")):
            btn = QPushButton(f"Move {d}")
            btn.clicked.connect(lambda _c=False, dd=d: self.move(dd))
            controls.addWidget(btn, 1 + idx // 2, idx % 2)

        for idx, label in enumerate(("Q (Left)", "E (Right)")):
            btn = QPushButton(f"Turn {label}")
            action = "turn_left" if idx == 0 else "turn_right"
            btn.clicked.connect(lambda _c=False, a=action: self._backend._handle_action(a))
            controls.addWidget(btn, 3, idx)

        right_layout.addStretch()
        root.addWidget(right, stretch=1)

        # Deferred start so layout has settled.
        QTimer.singleShot(0, self._deferred_start)

    def _deferred_start(self) -> None:
        self._backend.start(self._viewport)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_text)
        self._status_timer.start(400)

        self.refresh_from_engine_view()

        if self._sweep_enabled:
            self._start_sweep()

    # -- Facing label --------------------------------------------------------

    def _on_facing_changed(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        self._facing_label.setText(f"Facing: {d if d in {'N','S','E','W'} else '?'}")

    # -- Engine interaction --------------------------------------------------

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
        ready = self._backend.is_ready()
        if self._last_view is None:
            vl = "view: <none>"
        else:
            pos = self._last_view.pos
            vl = (
                f"view: pos=({pos['row']},{pos['col']}) "
                f"moves={self._last_view.move_count} "
                f"visited={self._last_view.visited_count}"
            )
        lines = [
            f"backend_ready={ready}",
            "renderer=Pygame (raycaster)",
            self._sweep_status_line(),
            vl,
            "messages="
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

    # -- Sweep ---------------------------------------------------------------

    def _sweep_status_line(self) -> str:
        if not self._sweep_enabled:
            return "sweep=disabled"
        total = len(self._sweep_actions)
        st = "done" if self._sweep_done else "running"
        return f"sweep={st} step={self._sweep_idx}/{total} errors={len(self._sweep_errors)}"

    def _start_sweep(self) -> None:
        self._sweep_actions = _build_sweep_actions(self._engine.maze)
        self._sweep_idx = 0
        self._sweep_done = False
        self._sweep_errors.clear()
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
        else:
            summary = (
                f"SWEEP PASS: {len(self._sweep_actions)} actions, no errors detected"
            )
            print(summary)
            log.info(summary)

        self._last_engine_messages = [summary]
        self._update_status_text()

        if self._auto_quit_on_sweep_done:
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(300, lambda: self._shutdown_and_quit(app))

    def _run_sweep_step(self) -> None:
        if self._sweep_done:
            return
        if not self._backend.is_ready():
            self._record_sweep_error("Pygame backend not ready during sweep")
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
                if msg in {
                    "Blocked path.", "Invalid direction.",
                    "Unknown command.", "No pending puzzle.",
                }:
                    self._record_sweep_error(
                        f"Engine move error at step {self._sweep_idx}: {msg}",
                    )
                    break
        elif action == "face":
            self._canvas.set_view_direction(payload)
            self._last_engine_messages = [f"face {payload}"]

        if self._sweep_errors:
            self._finish_sweep()

    def _shutdown_and_quit(self, app: QApplication) -> None:
        self._backend.stop()
        self.close()
        QTimer.singleShot(150, app.quit)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._backend.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pygame debug harness for MazeCanvas")
    p.add_argument("--size", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--gates", type=int, default=2)
    p.add_argument("--hide-unvisited", action="store_true")
    p.add_argument("--sweep-angles", action="store_true")
    p.add_argument("--sweep-step-ms", type=int, default=200)
    p.add_argument("--auto-quit-on-sweep-done", action="store_true")
    p.add_argument("--auto-quit-seconds", type=float, default=0.0)
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    engine, tmpdir = _build_engine(
        size=args.size, seed=args.seed, gates=args.gates,
        reveal_all=not args.hide_unvisited,
    )
    log.info("Built harness engine with size=%d seed=%d gates=%d",
             args.size, args.seed, args.gates)

    app = QApplication.instance() or QApplication(sys.argv)
    window = HarnessWindow(
        engine=engine,
        sweep_angles=args.sweep_angles,
        sweep_step_ms=args.sweep_step_ms,
        auto_quit_on_sweep_done=args.auto_quit_on_sweep_done,
    )
    app.aboutToQuit.connect(window.close)
    window.show()

    if args.auto_quit_seconds > 0:
        QTimer.singleShot(
            int(args.auto_quit_seconds * 1000),
            lambda: window._shutdown_and_quit(app),
        )

    exit_code = app.exec()
    tmpdir.cleanup()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
