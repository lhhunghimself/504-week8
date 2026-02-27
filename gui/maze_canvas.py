"""MazeCanvas — QWidget with pluggable 3D renderer backend.

Contract: interfaces.md §7.3 (Team 2 — MazeCanvas)

The canvas always renders a 2D QPainter minimap.  When a 3D backend is
available (Godot or Panda3D), snapshot data is forwarded to the backend
and user input events flow back.

Signals:
    direction_clicked(str)  "N" | "S" | "E" | "W"

Slots:
    update_maze(MazeSnapshot)
    highlight_player(tuple[int,int])
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from gui.renderers.base_backend import BaseBackend

if TYPE_CHECKING:
    from main import CellView, MazeSnapshot

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# QPainter fallback style constants
# ---------------------------------------------------------------------------

CELL_PX = 64
WALL_PX = 4
PASSAGE_PX = 6

COLOR_FOG = QColor("#1a1a2e")
COLOR_VISIBLE = QColor("#16213e")
COLOR_START = QColor("#0f3460")
COLOR_EXIT = QColor("#533483")
COLOR_PLAYER = QColor("#e94560")
COLOR_GATE = QColor("#f5a623")
COLOR_GATE_SOLVED = QColor("#53bf6a")
COLOR_PASSAGE = QColor("#00ff41")
COLOR_GRID = QColor("#333355")
COLOR_TEXT = QColor("#00ff41")


@dataclass
class _CellState:
    """Internal per-cell render state for diffing."""
    row: int
    col: int
    kind: str
    visible: bool
    is_player: bool
    has_gate: bool
    solved: bool
    connections: tuple[str, ...]

    @classmethod
    def from_cell_view(cls, cv: CellView) -> _CellState:
        return cls(
            row=cv.row, col=cv.col, kind=cv.kind,
            visible=cv.visible, is_player=cv.is_player,
            has_gate=cv.has_gate, solved=cv.solved,
            connections=tuple(cv.connections),
        )


class MazeCanvas(QWidget):
    """Maze renderer — 3D backend + 2D QPainter minimap."""

    direction_clicked = pyqtSignal(str)
    godot_process_started = pyqtSignal(int)
    facing_changed = pyqtSignal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        use_godot: bool = True,
        godot_parent_widget: QWidget | None = None,
        backend: BaseBackend | None = None,
    ) -> None:
        super().__init__(parent)
        self._width = 0
        self._height = 0
        self._cells: dict[tuple[int, int], _CellState] = {}
        self._player_pos: tuple[int, int] | None = None
        self._last_changed: list[tuple[int, int]] = []
        self._facing_dir: str = "S"
        self._fallback_reason: str | None = None
        self.setMinimumSize(200, 200)

        # Backend setup
        self._backend: BaseBackend | None = None
        self._backend_available = False

        if backend is not None:
            self._init_backend(backend)
        elif use_godot:
            self._init_godot_backend(godot_parent_widget)
        else:
            self._fallback_reason = "3D disabled"

        if self._fallback_reason:
            log.warning("3D mode unavailable: %s", self._fallback_reason)

    def _init_backend(self, backend: BaseBackend) -> None:
        """Attach an externally-provided backend."""
        self._backend = backend
        self._backend_available = True
        backend.on_direction(self._on_backend_direction)
        backend.on_facing(self._on_backend_facing)

    def _init_godot_backend(self, godot_parent_widget: QWidget | None) -> None:
        """Try to set up the Godot backend."""
        from gui.renderers.godot_backend import GodotBackend

        reason = GodotBackend.check_availability()
        if reason:
            self._fallback_reason = reason
            return

        godot = GodotBackend(godot_parent_widget=godot_parent_widget)
        godot.on_fallback(self._on_backend_fallback)
        godot.process_started.connect(self.godot_process_started.emit)
        self._init_backend(godot)
        godot.start(self)

    def _on_backend_direction(self, direction: str) -> None:
        self._set_facing_dir(direction)
        self.direction_clicked.emit(direction)

    def _on_backend_facing(self, direction: str) -> None:
        self._set_facing_dir(direction)

    def _on_backend_fallback(self, reason: str) -> None:
        self._fallback_reason = reason
        self._backend_available = False
        log.warning("3D mode unavailable: %s", reason)
        if self._width > 0 and self._height > 0:
            ideal_w = self._width * CELL_PX + WALL_PX
            ideal_h = self._height * CELL_PX + WALL_PX
            self.setMinimumSize(ideal_w, ideal_h)
        self.update()

    # -- Public slots -------------------------------------------------------

    def update_maze(self, snapshot: MazeSnapshot) -> None:
        old = self._cells
        self._width = snapshot.width
        self._height = snapshot.height

        new_cells: dict[tuple[int, int], _CellState] = {}
        changed: list[tuple[int, int]] = []
        player_pos: tuple[int, int] | None = None

        for cv in snapshot.cells:
            key = (cv.row, cv.col)
            state = _CellState.from_cell_view(cv)
            new_cells[key] = state
            if cv.is_player:
                player_pos = key
            if key not in old or old[key] != state:
                changed.append(key)

        for key in old:
            if key not in new_cells:
                changed.append(key)

        self._cells = new_cells
        self._player_pos = player_pos
        self._last_changed = changed

        ideal_w = self._width * CELL_PX + WALL_PX
        ideal_h = self._height * CELL_PX + WALL_PX
        self.setMinimumSize(ideal_w, ideal_h)

        if self._backend_available and self._backend is not None:
            cells_data = [
                {
                    "row": cv.row, "col": cv.col, "kind": cv.kind,
                    "visible": cv.visible, "is_player": cv.is_player,
                    "has_gate": cv.has_gate, "solved": cv.solved,
                    "connections": list(cv.connections),
                }
                for cv in snapshot.cells
            ]
            self._backend.send_maze_update({
                "width": snapshot.width,
                "height": snapshot.height,
                "cells": cells_data,
            })
        self.update()

    def highlight_player(self, pos: tuple[int, int]) -> None:
        self._player_pos = pos
        if self._backend_available and self._backend is not None:
            self._backend.send_highlight_player(pos[0], pos[1])
        else:
            self.update()

    def set_view_direction(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d not in {"N", "S", "E", "W"}:
            return
        self._set_facing_dir(d)
        if self._backend_available and self._backend is not None:
            self._backend.send_view_direction(d)

    def facing_direction(self) -> str:
        return self._facing_dir

    def _set_facing_dir(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d not in {"N", "S", "E", "W"}:
            return
        if d == self._facing_dir:
            return
        self._facing_dir = d
        self.facing_changed.emit(d)
        self.update()

    # -- Test query methods -------------------------------------------------

    def cell_count(self) -> int:
        return len(self._cells)

    def cell_style(self, row: int, col: int) -> str:
        state = self._cells.get((row, col))
        if state is None:
            return "missing"
        if not state.visible:
            return "fog"
        if state.is_player:
            return "player"
        if state.has_gate and not state.solved:
            return "gate"
        if state.has_gate and state.solved:
            return "gate_solved"
        if state.kind == "start":
            return "start"
        if state.kind == "exit":
            return "exit"
        return "visible"

    def has_player_indicator(self, row: int, col: int) -> bool:
        state = self._cells.get((row, col))
        return state is not None and state.is_player

    def has_gate_indicator(self, row: int, col: int) -> bool:
        state = self._cells.get((row, col))
        return state is not None and state.has_gate

    def has_connection(self, row: int, col: int, direction: str) -> bool:
        state = self._cells.get((row, col))
        return state is not None and direction in state.connections

    def click_cell(self, row: int, col: int) -> None:
        if self._player_pos is None:
            return
        pr, pc = self._player_pos
        dr, dc = row - pr, col - pc
        direction_map = {(-1, 0): "N", (1, 0): "S", (0, -1): "W", (0, 1): "E"}
        direction = direction_map.get((dr, dc))
        if direction:
            self._set_facing_dir(direction)
            self.direction_clicked.emit(direction)

    def last_update_changed_cells(self) -> list[tuple[int, int]]:
        return list(self._last_changed)

    # -- QPainter fallback rendering ----------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._cells:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for (r, c), state in self._cells.items():
            self._draw_cell(painter, r, c, state)
        if self._fallback_reason:
            self._draw_fallback_banner(painter)
        painter.end()

    def _draw_fallback_banner(self, painter: QPainter) -> None:
        banner_h = 22
        w = self.width()
        painter.fillRect(QRectF(0, 0, w, banner_h), QColor(40, 40, 40, 200))
        font = QFont("monospace", 9)
        painter.setFont(font)
        painter.setPen(QColor(255, 200, 60))
        painter.drawText(
            QRectF(4, 0, w - 8, banner_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"2D fallback: {self._fallback_reason}",
        )

    def _cell_rect(self, row: int, col: int) -> QRectF:
        x = col * CELL_PX + WALL_PX / 2
        y = row * CELL_PX + WALL_PX / 2
        return QRectF(x, y, CELL_PX - WALL_PX, CELL_PX - WALL_PX)

    def _draw_cell(self, painter: QPainter, row: int, col: int, state: _CellState) -> None:
        rect = self._cell_rect(row, col)
        bg = self._bg_color(state)
        painter.fillRect(rect, bg)
        painter.setPen(QPen(COLOR_GRID, WALL_PX))
        painter.drawRect(rect)
        if state.visible:
            self._draw_connections(painter, row, col, state)
        if state.is_player:
            self._draw_player(painter, rect)
        elif state.has_gate and not state.solved:
            self._draw_gate(painter, rect)
        elif state.has_gate and state.solved:
            self._draw_solved_gate(painter, rect)
        elif state.kind == "exit" and state.visible:
            self._draw_exit(painter, rect)

    def _bg_color(self, state: _CellState) -> QColor:
        if not state.visible:
            return COLOR_FOG
        if state.is_player:
            return COLOR_PLAYER.darker(150)
        if state.kind == "start":
            return COLOR_START
        if state.kind == "exit":
            return COLOR_EXIT
        return COLOR_VISIBLE

    def _draw_player(self, painter: QPainter, rect: QRectF) -> None:
        cx, cy = rect.center().x(), rect.center().y()
        r = min(rect.width(), rect.height()) * 0.34

        points_by_dir: dict[str, list[tuple[float, float]]] = {
            "N": [(0.0, -1.0), (-0.8, 0.75), (0.8, 0.75)],
            "S": [(0.0, 1.0), (-0.8, -0.75), (0.8, -0.75)],
            "E": [(1.0, 0.0), (-0.75, -0.8), (-0.75, 0.8)],
            "W": [(-1.0, 0.0), (0.75, -0.8), (0.75, 0.8)],
        }
        points_norm = points_by_dir.get(self._facing_dir)
        if not points_norm:
            painter.setBrush(COLOR_PLAYER)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
            return

        poly = QPolygonF([
            QPointF(cx + dx * r, cy + dy * r)
            for dx, dy in points_norm
        ])
        painter.setBrush(COLOR_PLAYER)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawPolygon(poly)

    def _draw_gate(self, painter: QPainter, rect: QRectF) -> None:
        font = QFont("monospace", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(COLOR_GATE)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "\U0001f512")

    def _draw_solved_gate(self, painter: QPainter, rect: QRectF) -> None:
        font = QFont("monospace", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(COLOR_GATE_SOLVED)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "\u2713")

    def _draw_exit(self, painter: QPainter, rect: QRectF) -> None:
        font = QFont("monospace", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(COLOR_TEXT)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "EXIT")

    def _draw_connections(self, painter: QPainter, row: int, col: int, state: _CellState) -> None:
        rect = self._cell_rect(row, col)
        cx, cy = rect.center().x(), rect.center().y()
        pen = QPen(COLOR_PASSAGE, PASSAGE_PX)
        painter.setPen(pen)
        for d in state.connections:
            if d == "N":
                painter.drawLine(int(cx), int(rect.top()), int(cx), int(cy))
            elif d == "S":
                painter.drawLine(int(cx), int(cy), int(cx), int(rect.bottom()))
            elif d == "W":
                painter.drawLine(int(rect.left()), int(cy), int(cx), int(cy))
            elif d == "E":
                painter.drawLine(int(cx), int(cy), int(rect.right()), int(cy))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._cells or self._player_pos is None:
            return
        if self._backend_available:
            return
        x, y = event.position().x(), event.position().y()
        col = int(x // CELL_PX)
        row = int(y // CELL_PX)
        if 0 <= row < self._height and 0 <= col < self._width:
            self.click_cell(row, col)

    # -- Cleanup ------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._backend is not None:
            self._backend.stop()
        super().closeEvent(event)
