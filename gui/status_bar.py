"""StatusBar — game progress display.

Contract: interfaces.md §7.3 (Team 1 — StatusBar).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from main import GameView


class StatusBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self._label = QLabel("—")
        self._label.setStyleSheet("font-family: monospace; color: #0f0;")
        layout.addWidget(self._label)

    def update_status(self, view: GameView) -> None:
        parts = [
            f"Pos: ({view.pos['row']}, {view.pos['col']})",
            f"Moves: {view.move_count}",
            f"Visited: {view.visited_count}",
        ]
        self._label.setText("  |  ".join(parts))

    def status_text(self) -> str:
        return self._label.text()
