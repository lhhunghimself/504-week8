"""GUI entry point — creates the window and wires all widgets to the engine.

Contract: interfaces.md §7.4 / §7.5.
Usage:
    python gui_main.py [--size N] [--seed N] [--gates N] [--reset-game] [--renderer panda3d|godot|pygame|qpaint]
    python main.py --gui [...]
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from main import (
    Command,
    GameEngine,
    StartupConfig,
    _build_maze,
    _initialize_question_bank,
    _parse_startup_flags,
    _utc_now_iso,
)

from gui.controller import GameController

log = logging.getLogger(__name__)

# -- Conditional imports for team widgets (may not exist yet) ----------------

try:
    from gui.forms_panel import FormsPanel
except ImportError:
    FormsPanel = None  # type: ignore[assignment,misc]

try:
    from gui.puzzle_dialog import PuzzleDialog
except ImportError:
    PuzzleDialog = None  # type: ignore[assignment,misc]

try:
    from gui.status_bar import StatusBar
except ImportError:
    StatusBar = None  # type: ignore[assignment,misc]

try:
    from gui.score_board import ScoreBoard
except ImportError:
    ScoreBoard = None  # type: ignore[assignment,misc]

try:
    from gui.maze_canvas import MazeCanvas
except ImportError:
    MazeCanvas = None  # type: ignore[assignment,misc]


_STYLESHEET = """
QMainWindow { background-color: #1a1a2e; }
QWidget { background-color: #1a1a2e; color: #e0e0e0; font-size: 13px; }
QLabel { color: #0f0; }
QPushButton {
    background-color: #16213e; color: #0f0; border: 1px solid #0f0;
    padding: 6px 14px; border-radius: 4px; font-weight: bold;
}
QPushButton:hover { background-color: #0f3460; }
QPushButton:disabled { color: #555; border-color: #333; background-color: #111; }
QLineEdit {
    background-color: #0d1117; color: #0f0; border: 1px solid #0f0;
    padding: 5px; border-radius: 3px;
}
QTextEdit {
    background-color: #0d1117; color: #0f0; border: 1px solid #333;
    border-radius: 3px;
}
QTableWidget {
    background-color: #0d1117; color: #0f0; gridline-color: #333;
    border: 1px solid #333;
}
QHeaderView::section {
    background-color: #16213e; color: #0f0; border: 1px solid #333;
    padding: 4px; font-weight: bold;
}
"""


class _StubMapWidget(QWidget):
    """Placeholder for MazeCanvas until Team 2 delivers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("MAZE MAP (canvas pending)"))
        self._display = QTextEdit()
        self._display.setReadOnly(True)
        self._display.setStyleSheet(
            "font-family: 'Courier New', monospace; font-size: 18px; "
            "background: #111; color: #0f0; padding: 12px;"
        )
        layout.addWidget(self._display)

    def update_from_view(self, view: object) -> None:
        text = getattr(view, "map_text", "")
        self._display.setPlainText(text)


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: GameController,
        repo: object,
        *,
        use_godot: bool = False,
        renderer: str = "qpaint",
    ) -> None:
        super().__init__()
        self.setWindowTitle("Hack the Maze — PyQt6")
        self.setMinimumSize(900, 650)

        self._controller = controller
        self._repo = repo
        self._renderer = renderer
        self._pygame_viewport: QWidget | None = None
        self._pygame_embedded = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # -- Left panel: 3D viewport + 2D minimap --
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._facing_label = QLabel("Facing: S")
        self._facing_label.setStyleSheet("font-family: monospace; color: #9be79b; padding: 4px;")
        left_layout.addWidget(self._facing_label)

        # Godot embedding state (only used when renderer=="godot")
        self._godot_embed_timer: QTimer | None = None
        self._godot_embed_pid: int | None = None
        self._godot_embed_attempts = 0
        self._godot_foreign_window: QWindow | None = None
        self._godot_container: QWidget | None = None
        self._can_embed_godot = (
            shutil.which("wmctrl") is not None
            and os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland"
        )

        if MazeCanvas is not None:
            # 3D viewport host widget
            self._viewport_host = QWidget()
            self._viewport_host.setObjectName("viewportHost")
            self._viewport_host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
            self._viewport_host.setMinimumHeight(220)
            self._viewport_host.setStyleSheet("background-color: #000; border: 1px solid #333;")
            # Keep resize/show events flowing for both Godot and Panda3D paths.
            self._viewport_host.installEventFilter(self)

            self._viewport_host_layout = QVBoxLayout(self._viewport_host)
            self._viewport_host_layout.setContentsMargins(0, 0, 0, 0)

            if renderer == "panda3d":
                # For Panda3D: give the viewport host an expanding size policy so
                # Qt allocates it the majority of the vertical space in the splitter.
                from PyQt6.QtWidgets import QSizePolicy
                self._viewport_host.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding,
                )
                self._canvas = self._create_panda3d_canvas()
                # The 2D canvas shows the minimap strip; cap its height.
                self._canvas.setMaximumHeight(200)
            elif renderer == "pygame":
                from PyQt6.QtWidgets import QSizePolicy
                self._viewport_host.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding,
                )
                self._canvas = self._create_pygame_canvas()
                if self._pygame_embedded:
                    self._canvas.setMaximumHeight(200)
                else:
                    # Import fallback path: hide empty viewport host and let
                    # the 2D map use the full left panel.
                    self._viewport_host.hide()
            elif renderer == "qpaint":
                from PyQt6.QtWidgets import QSizePolicy
                self._viewport_host.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Expanding,
                )
                self._canvas = self._create_qpaint_canvas()
                self._canvas.setMaximumHeight(200)
            elif renderer == "godot":
                self._godot_placeholder = QLabel(
                    "Waiting for Godot viewport..."
                    if self._can_embed_godot else
                    "Embedded Godot unavailable (requires X11 + wmctrl)"
                )
                self._godot_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._godot_placeholder.setStyleSheet("color: #888;")
                self._viewport_host_layout.addWidget(self._godot_placeholder)
                self._canvas = MazeCanvas(use_godot=use_godot, godot_parent_widget=self._viewport_host)
            else:
                self._canvas = MazeCanvas(use_godot=False)

            left_splitter = QSplitter(Qt.Orientation.Vertical)
            left_splitter.addWidget(self._viewport_host)
            left_splitter.addWidget(self._canvas)
            if renderer in ("panda3d", "qpaint") or (renderer == "pygame" and self._pygame_embedded):
                left_splitter.setStretchFactor(0, 3)
                left_splitter.setStretchFactor(1, 1)
                left_splitter.setSizes([500, 150])
            elif renderer == "pygame":
                left_splitter.setStretchFactor(0, 0)
                left_splitter.setStretchFactor(1, 1)
                left_splitter.setSizes([0, 650])
            else:
                left_splitter.setSizes([360, 280])
            left_layout.addWidget(left_splitter)
        else:
            self._viewport_host = None
            self._viewport_host_layout = None
            self._canvas = _StubMapWidget()
            left_layout.addWidget(self._canvas)
        splitter.addWidget(left)

        # -- Right panel: Team 1 widgets --
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._forms = FormsPanel() if FormsPanel else QLabel("FormsPanel not available")
        right_layout.addWidget(self._forms)

        self._puzzle = PuzzleDialog() if PuzzleDialog else QLabel("PuzzleDialog not available")
        right_layout.addWidget(self._puzzle)

        self._status = StatusBar() if StatusBar else QLabel("StatusBar not available")
        right_layout.addWidget(self._status)

        self._scores = ScoreBoard() if ScoreBoard else QLabel("ScoreBoard not available")
        right_layout.addWidget(self._scores)

        splitter.addWidget(right)
        splitter.setSizes([400, 500])

        self._wire_signals()

    def _create_panda3d_canvas(self) -> MazeCanvas:
        """Create a MazeCanvas backed by the Panda3D in-process renderer."""
        from gui.renderers.panda3d_backend import Panda3DBackend

        backend = Panda3DBackend()
        canvas = MazeCanvas(use_godot=False, backend=backend)
        return canvas

    def _create_pygame_canvas(self) -> MazeCanvas:
        """Create a MazeCanvas backed by the Pygame raycaster."""
        try:
            from gui.renderers.pygame_backend import PygameBackend, PygameViewport
        except ImportError:
            self._pygame_embedded = False
            log.warning("Pygame not available, falling back to 2D-only mode")
            return MazeCanvas(use_godot=False)

        backend = PygameBackend()
        self._pygame_viewport = PygameViewport(backend, self._viewport_host)
        self._viewport_host_layout.addWidget(self._pygame_viewport)
        self._pygame_embedded = True
        canvas = MazeCanvas(use_godot=False, backend=backend)
        return canvas

    def _create_qpaint_canvas(self) -> MazeCanvas:
        """Create a MazeCanvas backed by the QPainter pre-rendered backend."""
        from gui.renderers.qpaint_backend import QPaintBackend

        backend = QPaintBackend()
        canvas = MazeCanvas(use_godot=False, backend=backend)
        return canvas

    def _ensure_qpaint_started(self) -> None:
        """Start QPaint backend lazily once the viewport host is shown."""
        if self._renderer != "qpaint":
            return
        if not isinstance(self._canvas, MazeCanvas):
            return
        if self._viewport_host is None:
            return
        backend = self._canvas._backend
        if backend is None:
            return
        if not backend.is_ready():
            backend.start(self._viewport_host)
        elif hasattr(backend, "_handle_resize"):
            backend._handle_resize()

    def _ensure_panda3d_started(self) -> None:
        """Start Panda3D backend lazily once the viewport host is shown."""
        if self._renderer != "panda3d":
            return
        if not isinstance(self._canvas, MazeCanvas):
            return
        if self._viewport_host is None:
            return
        backend = self._canvas._backend
        if backend is None:
            return
        if not backend.is_ready():
            # Starting too early (before native show/map) can trigger GLX drawable errors.
            backend.start(self._viewport_host)
            # The Qt layout engine may not have assigned final sizes yet.
            # Poll until the Panda3D window matches the host widget, giving up after ~1s.
            self._schedule_panda3d_size_sync()
        elif hasattr(backend, "_handle_resize"):
            backend._handle_resize()

    def _schedule_panda3d_size_sync(self, _attempts: int = 0) -> None:
        """Poll until the Panda3D window matches the host widget size, then stop.

        The Qt layout engine finalises child-widget sizes asynchronously after
        ``show()``.  We retry with exponential back-off for up to ~1 second so
        the Panda3D sub-window always fills its host.
        """
        if self._viewport_host is None or not isinstance(self._canvas, MazeCanvas):
            return
        backend = self._canvas._backend
        if backend is None or not backend.is_ready():
            return
        backend._handle_resize()

        # Compare in physical pixels (Qt uses device-independent pixels).
        try:
            dpr = float(self._viewport_host.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        host_px_w = max(1, int(round(self._viewport_host.width() * dpr)))
        host_px_h = max(1, int(round(self._viewport_host.height() * dpr)))

        base = getattr(backend, "_base", None)
        win = base.win if base is not None else None
        if win is None:
            return
        already_correct = win.getXSize() == host_px_w and win.getYSize() == host_px_h

        if already_correct or _attempts >= 8:
            return
        delay_ms = min(50 * (2 ** _attempts), 400)
        QTimer.singleShot(
            delay_ms,
            lambda: self._schedule_panda3d_size_sync(_attempts + 1),
        )

    def _wire_signals(self) -> None:
        c = self._controller

        # Controller -> widgets
        if FormsPanel and isinstance(self._forms, FormsPanel):
            c.view_changed.connect(self._forms.update_view)
            c.messages_ready.connect(self._forms.show_messages)

        if PuzzleDialog and isinstance(self._puzzle, PuzzleDialog):
            c.view_changed.connect(lambda v: self._puzzle.show_puzzle(v.pending_puzzle))
            c.hint_options_ready.connect(self._puzzle.show_hint_options)
            c.hint_result_ready.connect(self._puzzle.show_hint_result)

        if StatusBar and isinstance(self._status, StatusBar):
            c.view_changed.connect(self._status.update_status)

        if ScoreBoard and isinstance(self._scores, ScoreBoard):
            c.game_completed.connect(self._on_game_completed)

        if MazeCanvas is not None and isinstance(self._canvas, MazeCanvas):
            c.view_changed.connect(
                lambda v: self._canvas.update_maze(v.maze_snapshot) if v.maze_snapshot else None
            )
            self._canvas.direction_clicked.connect(
                lambda d: c.on_command(Command(verb="go", args=[d]))
            )
            self._canvas.godot_process_started.connect(self._on_godot_process_started)
            self._canvas.facing_changed.connect(self._on_facing_changed)
            self._on_facing_changed(self._canvas.facing_direction())
        elif isinstance(self._canvas, _StubMapWidget):
            c.view_changed.connect(self._canvas.update_from_view)

        # Widgets -> controller
        if FormsPanel and isinstance(self._forms, FormsPanel):
            self._forms.command_issued.connect(c.on_command)

        if PuzzleDialog and isinstance(self._puzzle, PuzzleDialog):
            self._puzzle.answer_submitted.connect(
                lambda text: c.on_command(Command(verb="answer", args=[text]))
            )
            self._puzzle.hint_requested.connect(
                lambda t: c.on_command(Command(verb="hint", args=[t] if t else []))
            )

    def _on_godot_process_started(self, pid: int) -> None:
        if not self._can_embed_godot or self._viewport_host is None:
            return
        if self._godot_container is not None:
            return
        self._godot_embed_pid = pid
        self._godot_embed_attempts = 0
        if self._godot_embed_timer is None:
            self._godot_embed_timer = QTimer(self)
            self._godot_embed_timer.timeout.connect(self._poll_embed_godot_window)
        self._godot_embed_timer.start(150)

    def _poll_embed_godot_window(self) -> None:
        pid = self._godot_embed_pid
        if pid is None:
            if self._godot_embed_timer:
                self._godot_embed_timer.stop()
            return

        wid = self._find_window_id_for_pid(pid)
        if wid is not None:
            self._attach_godot_window(wid)
            if self._godot_embed_timer:
                self._godot_embed_timer.stop()
            return

        self._godot_embed_attempts += 1
        if self._godot_embed_attempts > 40:
            if self._godot_embed_timer:
                self._godot_embed_timer.stop()
            if isinstance(self._godot_placeholder, QLabel):
                self._godot_placeholder.setText("Could not embed Godot window; using external window.")

    def _find_window_id_for_pid(self, pid: int) -> int | None:
        try:
            out = subprocess.check_output(["wmctrl", "-lp"], text=True, stderr=subprocess.STDOUT)
        except Exception:
            return None

        matches: list[tuple[int, str]] = []
        for line in out.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 3:
                continue
            win_hex = parts[0]
            try:
                line_pid = int(parts[2])
            except ValueError:
                continue
            if line_pid != pid:
                continue
            try:
                win_id = int(win_hex, 16)
            except ValueError:
                continue
            matches.append((win_id, line))

        if not matches:
            return None

        for win_id, line in matches:
            if "HackTheMaze3D" in line or "Godot" in line:
                return win_id
        return matches[0][0]

    def _attach_godot_window(self, win_id: int) -> None:
        if self._viewport_host is None or self._viewport_host_layout is None:
            return
        if self._godot_container is not None:
            return

        foreign = QWindow.fromWinId(win_id)
        if foreign is None:
            return

        container = QWidget.createWindowContainer(foreign, self._viewport_host)
        container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        while self._viewport_host_layout.count() > 0:
            item = self._viewport_host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._viewport_host_layout.addWidget(container)

        self._godot_foreign_window = foreign
        self._godot_container = container
        log.info("Embedded Godot window id=%s into Qt host", hex(win_id))
        self._schedule_embed_refresh_kick()

    def _schedule_embed_refresh_kick(self) -> None:
        # A short sequence of geometry syncs avoids first-frame black viewport
        # issues on some X11 window manager / GPU combinations.
        for delay_ms in (0, 80, 220, 500):
            QTimer.singleShot(delay_ms, self._sync_embedded_godot_viewport)

    def _sync_embedded_godot_viewport(self) -> None:
        if self._viewport_host is None or self._godot_container is None:
            return
        host_w = max(1, self._viewport_host.width())
        host_h = max(1, self._viewport_host.height())
        if self._godot_container.width() != host_w or self._godot_container.height() != host_h:
            self._godot_container.resize(host_w, host_h)
        self._godot_container.updateGeometry()
        self._godot_container.update()
        self._viewport_host.update()

        if self._godot_foreign_window is not None:
            try:
                self._godot_foreign_window.setGeometry(0, 0, host_w, host_h)
                self._godot_foreign_window.requestActivate()
            except Exception:
                pass

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._viewport_host and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        }:
            if self._renderer == "godot":
                self._sync_embedded_godot_viewport()
            elif self._renderer == "panda3d":
                self._ensure_panda3d_started()
                self._sync_panda3d_viewport()
            elif self._renderer == "pygame":
                self._ensure_pygame_started()
                self._sync_pygame_viewport()
            elif self._renderer == "qpaint":
                self._ensure_qpaint_started()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._renderer == "panda3d":
            QTimer.singleShot(0, self._ensure_panda3d_started)
        elif self._renderer == "pygame":
            QTimer.singleShot(0, self._ensure_pygame_started)
        elif self._renderer == "qpaint":
            QTimer.singleShot(0, self._ensure_qpaint_started)

    def _sync_panda3d_viewport(self) -> None:
        if not isinstance(self._canvas, MazeCanvas):
            return
        backend = self._canvas._backend
        if backend is not None and hasattr(backend, "_handle_resize"):
            backend._handle_resize()

    def _ensure_pygame_started(self) -> None:
        """Start Pygame backend lazily once the viewport is shown."""
        if self._renderer != "pygame":
            return
        if not self._pygame_embedded:
            return
        if not isinstance(self._canvas, MazeCanvas):
            return
        viewport = getattr(self, "_pygame_viewport", None)
        if viewport is None:
            return
        backend = self._canvas._backend
        if backend is None:
            return
        if not backend.is_ready():
            backend.start(viewport)
        elif hasattr(backend, "_handle_resize"):
            backend._handle_resize()

    def _sync_pygame_viewport(self) -> None:
        if not self._pygame_embedded:
            return
        if not isinstance(self._canvas, MazeCanvas):
            return
        backend = self._canvas._backend
        if backend is not None and hasattr(backend, "_handle_resize"):
            backend._handle_resize()

    def _on_game_completed(self, metrics: dict) -> None:
        if ScoreBoard and isinstance(self._scores, ScoreBoard):
            try:
                scores = self._repo.top_scores()
                self._scores.show_scores(scores)
            except Exception:
                pass

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Forward key events to the canvas so the 3D backend receives them."""
        if (
            self._renderer in ("panda3d", "pygame", "qpaint")
            and MazeCanvas is not None
            and isinstance(self._canvas, MazeCanvas)
        ):
            self._canvas.keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        """Forward key release events to the canvas so the 3D backend receives them."""
        if (
            self._renderer in ("panda3d", "pygame", "qpaint")
            and MazeCanvas is not None
            and isinstance(self._canvas, MazeCanvas)
        ):
            self._canvas.keyReleaseEvent(event)
            return
        super().keyReleaseEvent(event)

    def _on_facing_changed(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d not in {"N", "S", "E", "W"}:
            d = "?"
        self._facing_label.setText(f"Facing: {d}")


def gui_main(config: StartupConfig | None = None) -> None:
    """Main GUI entry point, called from main.py --gui or standalone."""
    from db import HACKER_SEED_QUESTIONS, open_repo
    from puzzles import PuzzleRegistry

    app = QApplication.instance() or QApplication(sys.argv)

    if config is None:
        config = _parse_startup_flags(sys.argv[1:])

    save_path = Path("game_save.db")
    repo = open_repo(save_path)
    _initialize_question_bank(repo, HACKER_SEED_QUESTIONS, reset_game=config.reset_game)

    maze = _build_maze(config)
    puzzles = PuzzleRegistry()

    handle, ok = QInputDialog.getText(
        None, "Hack the Maze", "Enter your hacker handle:",
        text="anonymous",
    )
    if not ok or not handle.strip():
        handle = "anonymous"

    player = repo.get_or_create_player(handle.strip())
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": _utc_now_iso(),
        "visited": [{"row": maze.start.row, "col": maze.start.col}],
        "hints_used": 0,
        "maze_size": config.maze_size,
        "num_gates": config.num_gates,
        "maze_seed": config.maze_seed,
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = GameEngine(
        maze=maze, repo=repo, puzzles=puzzles,
        player_id=player_id, game_id=game_id,
    )

    controller = GameController(engine, threaded=True)

    window = MainWindow(
        controller, repo,
        use_godot=config.use_godot,
        renderer=config.renderer,
    )
    window.setStyleSheet(_STYLESHEET)
    window.show()

    controller.initialize()

    exit_code = app.exec()
    controller.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    gui_main()
