"""ScoreBoard — top scores table.

Contract: interfaces.md §7.3 (Team 1 — ScoreBoard).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class ScoreBoard(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Player", "Time (s)", "Moves", "Hints"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def show_scores(self, scores: list[dict]) -> None:
        self.table.setRowCount(len(scores))
        for row, score in enumerate(scores):
            handle = score.get("player_handle", "—")
            metrics = score.get("metrics", {})
            self.table.setItem(row, 0, QTableWidgetItem(str(handle)))
            self.table.setItem(row, 1, QTableWidgetItem(str(metrics.get("elapsed_seconds", "—"))))
            self.table.setItem(row, 2, QTableWidgetItem(str(metrics.get("moves", "—"))))
            self.table.setItem(row, 3, QTableWidgetItem(str(metrics.get("hints_used", "—"))))
