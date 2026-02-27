"""PuzzleDialog — puzzle prompt, answer input, hint options, and hint results.

Contract: interfaces.md §7.3 (Team 1 — PuzzleDialog).
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PuzzleDialog(QWidget):
    answer_submitted = pyqtSignal(str)
    hint_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        self.puzzle_area = QWidget()
        puzzle_layout = QVBoxLayout(self.puzzle_area)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #0f0;")
        puzzle_layout.addWidget(self.title_label)

        self.prompt_label = QLabel("")
        self.prompt_label.setWordWrap(True)
        puzzle_layout.addWidget(self.prompt_label)

        answer_row = QHBoxLayout()
        self.answer_input = QLineEdit()
        self.answer_input.setPlaceholderText("Type your answer...")
        self.answer_input.returnPressed.connect(self._submit_answer)
        answer_row.addWidget(self.answer_input)

        self.submit_button = QPushButton("Submit")
        self.submit_button.clicked.connect(self._submit_answer)
        answer_row.addWidget(self.submit_button)

        self.hint_button = QPushButton("Hint")
        self.hint_button.clicked.connect(lambda: self.hint_requested.emit(""))
        answer_row.addWidget(self.hint_button)

        puzzle_layout.addLayout(answer_row)

        self._hint_area = QWidget()
        self._hint_layout = QHBoxLayout(self._hint_area)
        self._hint_layout.setContentsMargins(0, 0, 0, 0)
        puzzle_layout.addWidget(self._hint_area)

        self._hint_result_label = QLabel("")
        self._hint_result_label.setWordWrap(True)
        puzzle_layout.addWidget(self._hint_result_label)

        self.hint_buttons: list[QPushButton] = []

        layout.addWidget(self.puzzle_area)
        self.puzzle_area.hide()

    def _submit_answer(self) -> None:
        text = self.answer_input.text().strip()
        if text:
            self.answer_submitted.emit(text)
            self.answer_input.clear()

    def show_puzzle(self, puzzle: dict | None) -> None:
        if puzzle is None:
            self.puzzle_area.hide()
            return

        self.title_label.setText(puzzle.get("title", ""))
        self.prompt_label.setText(puzzle.get("prompt", ""))
        self.answer_input.clear()
        self._hint_result_label.clear()
        self._clear_hint_buttons()
        self.hint_button.setVisible(True)
        self.puzzle_area.show()

    def show_hint_options(self, options: list[dict]) -> None:
        self._clear_hint_buttons()
        for opt in options:
            btn = QPushButton(opt["label"])
            hint_type = opt["type"]
            btn.clicked.connect(lambda checked, t=hint_type: self.hint_requested.emit(t))
            self._hint_layout.addWidget(btn)
            self.hint_buttons.append(btn)

    def show_hint_result(self, clue: str) -> None:
        self._hint_result_label.setText(clue)

    def _clear_hint_buttons(self) -> None:
        for btn in self.hint_buttons:
            self._hint_layout.removeWidget(btn)
            btn.deleteLater()
        self.hint_buttons.clear()
