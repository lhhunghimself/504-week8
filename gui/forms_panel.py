"""FormsPanel — room info, direction buttons, message area, and completion overlay.

Contract: interfaces.md §7.3 (Team 1 — FormsPanel).
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from main import Command, GameView


class FormsPanel(QWidget):
    command_issued = pyqtSignal(object)  # Command

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)

        self._room_title = QLabel("—")
        self._room_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self._room_title)

        self._room_desc = QLabel("")
        self._room_desc.setWordWrap(True)
        layout.addWidget(self._room_desc)

        nav_layout = QHBoxLayout()
        self.direction_buttons: dict[str, QPushButton] = {}
        for direction, label in [("N", "North"), ("W", "West"), ("S", "South"), ("E", "East")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, d=direction: self._on_direction(d))
            self.direction_buttons[direction] = btn
            nav_layout.addWidget(btn)
        layout.addLayout(nav_layout)

        self._message_area = QTextEdit()
        self._message_area.setReadOnly(True)
        self._message_area.setMaximumHeight(100)
        layout.addWidget(self._message_area)

        self.completion_overlay = QFrame()
        self.completion_overlay.setStyleSheet(
            "background-color: rgba(0, 40, 0, 200); color: #0f0;"
        )
        overlay_layout = QVBoxLayout(self.completion_overlay)
        self._completion_label = QLabel("ACCESS GRANTED — Root shell obtained!")
        self._completion_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #0f0;")
        overlay_layout.addWidget(self._completion_label)
        self.completion_overlay.setVisible(False)
        layout.addWidget(self.completion_overlay)

    def _on_direction(self, direction: str) -> None:
        self.command_issued.emit(Command(verb="go", args=[direction]))

    def update_view(self, view: GameView) -> None:
        self._room_title.setText(view.cell_title)
        self._room_desc.setText(view.cell_description)

        available = set(view.available_moves)
        for d, btn in self.direction_buttons.items():
            btn.setEnabled(d in available)

        self.completion_overlay.setVisible(view.is_complete)

    def show_messages(self, messages: list[str]) -> None:
        for msg in messages:
            self._message_area.append(msg)
