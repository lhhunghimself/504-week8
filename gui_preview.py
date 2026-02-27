#!/usr/bin/env python3
"""GUI Preview — visual mockup of Team 1 widgets with stub data.

Run:  python gui_preview.py

No engine, DB, or maze needed. Feeds dummy GameView data into
the real widgets so you can see the layout and click around.
"""
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from main import Command, GameView

from gui.forms_panel import FormsPanel
from gui.puzzle_dialog import PuzzleDialog
from gui.score_board import ScoreBoard
from gui.status_bar import StatusBar


# -- Stub maze map (text placeholder for Team 2's canvas) --------------------

STUB_MAPS = [
    " @──.──.\n │     │\n .  .──.\n │  │   \n .──.──X",
    " S──@──.\n │     │\n .  .──.\n │  │   \n .──.──X",
    " S──S──.\n │     │\n .  @──.\n │  │   \n .──.──X",
]

ROOMS = [
    ("Ingress Port", "You jack into the corporate network. Neon traces flicker."),
    ("Data Corridor", "Encrypted packets stream past. A firewall gate blocks east."),
    ("Cache Nexus", "Volatile memory banks hum. Two corridors branch south and east."),
]

DUMMY_PUZZLE = {
    "puzzle_id": "gate-fw-01",
    "title": "Firewall Lattice",
    "prompt": "What built-in Python function returns the number of items in a container?",
}

HINT_OPTIONS = [
    {"type": "letter", "label": "First letter (-1pt)", "cost": 1},
    {"type": "count", "label": "Character count (-1pt)", "cost": 1},
    {"type": "category", "label": "Category (-1pt)", "cost": 1},
    {"type": "reveal", "label": "Progressive reveal (-2pt)", "cost": 2},
]

DUMMY_SCORES = [
    {"player_handle": "neo", "metrics": {"elapsed_seconds": 42, "moves": 5, "hints_used": 0}},
    {"player_handle": "trinity", "metrics": {"elapsed_seconds": 60, "moves": 8, "hints_used": 2}},
    {"player_handle": "morpheus", "metrics": {"elapsed_seconds": 95, "moves": 14, "hints_used": 5}},
]


class PreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quiz Maze — GUI Preview (stub data)")
        self.setMinimumSize(900, 650)
        self._step = 0

        self._apply_theme()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # -- Left: stub map display --
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("MAZE MAP (Team 2 canvas stub)"))
        self._map_display = QTextEdit()
        self._map_display.setReadOnly(True)
        self._map_display.setStyleSheet(
            "font-family: 'Courier New', monospace; font-size: 18px; "
            "background: #111; color: #0f0; padding: 12px;"
        )
        left_layout.addWidget(self._map_display)
        splitter.addWidget(left)

        # -- Right: Team 1 widgets --
        right = QWidget()
        right_layout = QVBoxLayout(right)

        self._forms = FormsPanel()
        right_layout.addWidget(self._forms)

        self._puzzle = PuzzleDialog()
        right_layout.addWidget(self._puzzle)

        self._status = StatusBar()
        right_layout.addWidget(self._status)

        self._scores = ScoreBoard()
        right_layout.addWidget(self._scores)

        splitter.addWidget(right)
        splitter.setSizes([400, 500])

        # -- Wire stub handlers --
        self._forms.command_issued.connect(self._on_command)
        self._puzzle.answer_submitted.connect(self._on_answer)
        self._puzzle.hint_requested.connect(self._on_hint)

        # -- Show initial state --
        self._scores.show_scores(DUMMY_SCORES)
        self._render_step()

    def _apply_theme(self):
        self.setStyleSheet("""
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
            QFrame { border: 1px solid #0f0; border-radius: 4px; }
        """)

    def _make_view(self, room_idx: int, puzzle: dict | None = None,
                   available: list[str] | None = None, complete: bool = False) -> GameView:
        title, desc = ROOMS[room_idx % len(ROOMS)]
        return GameView(
            pos={"row": room_idx, "col": 0},
            cell_title=title,
            cell_description=desc,
            available_moves=available or ["N", "E", "S", "W"],
            pending_puzzle=puzzle,
            is_complete=complete,
            move_count=self._step,
            map_text="",
            visited_count=self._step + 1,
        )

    def _render_step(self):
        idx = self._step % len(ROOMS)
        map_text = STUB_MAPS[idx % len(STUB_MAPS)]
        self._map_display.setPlainText(map_text)

        if idx == 1:
            view = self._make_view(idx, puzzle=DUMMY_PUZZLE, available=["N", "W"])
            self._puzzle.show_puzzle(DUMMY_PUZZLE)
        else:
            view = self._make_view(idx, available=["N", "E", "S"])
            self._puzzle.show_puzzle(None)

        self._forms.update_view(view)
        self._status.update_status(view)

    def _on_command(self, cmd: Command):
        self._forms.show_messages([f"> {cmd.verb} {' '.join(cmd.args)}"])
        self._step += 1

        if self._step >= 5:
            view = self._make_view(0, complete=True, available=[])
            self._forms.update_view(view)
            self._status.update_status(view)
            self._map_display.setPlainText(" S──S──S\n │     │\n S  S──S\n │  │   \n S──S──@")
            self._forms.show_messages(["ACCESS GRANTED — you have root!"])
            return

        self._render_step()

    def _on_answer(self, text: str):
        self._forms.show_messages([f"[answer] {text}"])
        if text.lower() == "len":
            self._forms.show_messages(["Correct! Firewall breached."])
            self._puzzle.show_puzzle(None)
            self._step += 1
            self._render_step()
        else:
            self._forms.show_messages(["Incorrect. Try again."])

    def _on_hint(self, hint_type: str):
        if hint_type == "":
            self._forms.show_messages(["[hint] Requesting options..."])
            self._puzzle.show_hint_options(HINT_OPTIONS)
        else:
            clues = {
                "letter": "Clue: the answer starts with 'l'",
                "count": "Clue: the answer is 3 characters",
                "category": "Clue: category is 'python'",
                "reveal": "Clue: l _ _",
            }
            clue = clues.get(hint_type, f"Clue for '{hint_type}': ???")
            self._puzzle.show_hint_result(clue)
            self._forms.show_messages([f"[hint:{hint_type}] {clue}"])


def main():
    app = QApplication(sys.argv)
    window = PreviewWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
