"""GUI entry point — creates the window and wires all widgets to the engine.

Contract: interfaces.md §7.4 / §7.5.
Usage:
    python gui_main.py [--size N] [--seed N] [--gates N] [--reset-game]
    python main.py --gui [...]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
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
    def __init__(self, controller: GameController, repo: object) -> None:
        super().__init__()
        self.setWindowTitle("Hack the Maze — PyQt6")
        self.setMinimumSize(900, 650)

        self._controller = controller
        self._repo = repo

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # -- Left panel: maze canvas or stub --
        if MazeCanvas is not None:
            self._canvas = MazeCanvas()
        else:
            self._canvas = _StubMapWidget()
        splitter.addWidget(self._canvas)

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

    def _on_game_completed(self, metrics: dict) -> None:
        if ScoreBoard and isinstance(self._scores, ScoreBoard):
            try:
                scores = self._repo.top_scores()
                self._scores.show_scores(scores)
            except Exception:
                pass


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

    window = MainWindow(controller, repo)
    window.setStyleSheet(_STYLESHEET)
    window.show()

    controller.initialize()

    exit_code = app.exec()
    controller.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    gui_main()
