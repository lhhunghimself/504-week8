"""MazeCanvas — QWidget bridge to a Godot 4 first-person 3D renderer.

Contract: interfaces.md §7.3 (Team 2 — MazeCanvas)

When Godot is available, the canvas:
  1. Starts a QWebSocketServer on a random port
  2. Launches Godot as a subprocess with --ws-port=PORT
     (optionally embedded into a provided native Qt host widget via --wid)
  3. Serializes MazeSnapshot as JSON and sends to Godot
  4. Receives direction commands from Godot via WebSocket
  5. Still renders the 2D grid in-app as a live minimap

When Godot is not available (or during tests), falls back to the built-in
QPainter grid renderer.

Signals:
    direction_clicked(str)  "N" | "S" | "E" | "W"

Slots:
    update_maze(MazeSnapshot)
    highlight_player(tuple[int,int])
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QProcess, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

try:
    from PyQt6.QtWebSockets import QWebSocket, QWebSocketServer
    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False

if TYPE_CHECKING:
    from main import CellView, MazeSnapshot

log = logging.getLogger(__name__)

GODOT_PROJECT_DIR = Path(__file__).resolve().parent.parent / "godot_maze"
GODOT_CONNECT_TIMEOUT_MS = 5000

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


def _find_godot() -> str | None:
    """Return the path to the Godot executable, or None."""
    for name in ("godot", "godot4", "godot-4", "Godot_v4"):
        path = shutil.which(name)
        if path:
            return path
    return None


class MazeCanvas(QWidget):
    """Maze renderer — Godot 3D when available, QPainter 2D fallback."""

    direction_clicked = pyqtSignal(str)
    godot_process_started = pyqtSignal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        use_godot: bool = True,
        godot_parent_widget: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._width = 0
        self._height = 0
        self._cells: dict[tuple[int, int], _CellState] = {}
        self._player_pos: tuple[int, int] | None = None
        self._last_changed: list[tuple[int, int]] = []
        self.setMinimumSize(200, 200)

        # Godot bridge state
        self._godot_exe = _find_godot() if use_godot else None
        self._fallback_reason = self._check_godot_fallback(use_godot)
        self._godot_available = self._fallback_reason is None
        self._ws_server: QWebSocketServer | None = None
        self._ws_client: QWebSocket | None = None
        self._godot_process: QProcess | None = None
        self._ws_port: int = 0
        self._pending_messages: list[str] = []
        self._connect_timeout: QTimer | None = None
        self._is_closing = False
        self._godot_stderr_tail: list[str] = []
        self._godot_parent_widget = godot_parent_widget

        if self._fallback_reason:
            log.warning("3D mode unavailable: %s", self._fallback_reason)

        if self._godot_available:
            self._start_ws_server()

    def _check_godot_fallback(self, use_godot: bool) -> str | None:
        """Return a human-readable reason for 2D fallback, or None if 3D is OK."""
        if not use_godot:
            return "3D disabled (--no-godot flag)"
        if self._godot_exe is None:
            return ("Godot not found on PATH — install Godot 4.2+ and ensure "
                    "'godot' is on your PATH (see README)")
        if not _HAS_WEBSOCKETS:
            return "PyQt6-WebSockets not installed (pip install PyQt6-WebSockets)"
        if not GODOT_PROJECT_DIR.is_dir():
            return f"Godot project directory not found: {GODOT_PROJECT_DIR}"
        return None

    # -- WebSocket server (Python side) -------------------------------------

    def _start_ws_server(self) -> None:
        self._ws_server = QWebSocketServer(
            "MazeCanvasBridge",
            QWebSocketServer.SslMode.NonSecureMode,
            self,
        )
        if self._ws_server.listen(port=0):
            self._ws_port = self._ws_server.serverPort()
            self._ws_server.newConnection.connect(self._on_godot_connected)
            log.info("WebSocket server listening on port %d", self._ws_port)
        else:
            self._fallback_to_2d("Failed to start WebSocket server")

    def _on_godot_connected(self) -> None:
        if self._ws_server is None:
            return
        if self._connect_timeout and self._connect_timeout.isActive():
            self._connect_timeout.stop()
        self._ws_client = self._ws_server.nextPendingConnection()
        if self._ws_client:
            self._ws_client.textMessageReceived.connect(self._on_godot_message)
            log.info("Godot connected via WebSocket")
            if self._pending_messages:
                for pending in self._pending_messages:
                    self._ws_client.sendTextMessage(pending)
                self._pending_messages.clear()

    def _on_godot_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("type") == "direction":
            value = msg.get("value", "")
            if value in ("N", "S", "E", "W"):
                self.direction_clicked.emit(value)

    def _send_to_godot(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        if self._ws_client:
            self._ws_client.sendTextMessage(text)
        else:
            self._pending_messages.append(text)

    # -- Godot subprocess management ----------------------------------------

    def _launch_godot(self) -> None:
        if self._godot_process is not None or not self._godot_exe or not self._godot_available:
            return

        self._godot_process = QProcess(self)
        self._godot_process.setWorkingDirectory(str(GODOT_PROJECT_DIR))
        self._godot_process.started.connect(self._on_godot_started)
        self._godot_process.errorOccurred.connect(self._on_godot_process_error)
        self._godot_process.finished.connect(self._on_godot_process_finished)
        self._godot_process.readyReadStandardError.connect(self._on_godot_stderr)
        self._godot_process.readyReadStandardOutput.connect(self._on_godot_stdout)
        args = ["--path", str(GODOT_PROJECT_DIR)]
        if (
            self._godot_parent_widget is not None
            and os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"
            and os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen"
        ):
            args.extend(["--single-window", "--display-driver", "x11", "--rendering-driver", "opengl3"])
        args.extend(["--", f"--ws-port={self._ws_port}"])
        log.info("Launching Godot: %s %s", self._godot_exe, " ".join(args))
        self._godot_process.start(self._godot_exe, args)
        self._start_connect_timeout()

    def _on_godot_started(self) -> None:
        if self._godot_process is None:
            return
        self.godot_process_started.emit(int(self._godot_process.processId()))

    def _start_connect_timeout(self) -> None:
        if self._connect_timeout is None:
            self._connect_timeout = QTimer(self)
            self._connect_timeout.setSingleShot(True)
            self._connect_timeout.timeout.connect(self._on_connect_timeout)
        self._connect_timeout.start(GODOT_CONNECT_TIMEOUT_MS)

    def _on_connect_timeout(self) -> None:
        if self._is_closing or not self._godot_available:
            return
        if self._ws_client is None:
            self._fallback_to_2d(
                "Godot did not connect to bridge within 5s "
                "(check that Godot 4.2+ launches and supports WebSocketPeer)"
            )

    def _on_godot_process_error(self, err: QProcess.ProcessError) -> None:
        if self._is_closing or not self._godot_available:
            return
        self._fallback_to_2d(f"Godot process error: {err.name}")

    def _on_godot_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._godot_process = None
        if self._is_closing or not self._godot_available:
            return
        detail = f"Godot exited (code={exit_code}, status={exit_status.name})"
        if self._godot_stderr_tail:
            detail = f"{detail} — {self._godot_stderr_tail[-1]}"
        self._fallback_to_2d(detail)

    def _on_godot_stderr(self) -> None:
        if self._godot_process is None:
            return
        chunk = bytes(self._godot_process.readAllStandardError()).decode("utf-8", errors="replace")
        if not chunk:
            return
        for line in chunk.splitlines():
            line = line.strip()
            if line:
                self._godot_stderr_tail.append(line)
        if len(self._godot_stderr_tail) > 10:
            self._godot_stderr_tail = self._godot_stderr_tail[-10:]
        log.warning("Godot stderr: %s", chunk.rstrip())

    def _on_godot_stdout(self) -> None:
        if self._godot_process is None:
            return
        chunk = bytes(self._godot_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if chunk:
            log.info("Godot stdout: %s", chunk.rstrip())

    def _fallback_to_2d(self, reason: str) -> None:
        self._fallback_reason = reason
        self._godot_available = False
        self._pending_messages.clear()
        log.warning("3D mode unavailable: %s", reason)

        if self._connect_timeout and self._connect_timeout.isActive():
            self._connect_timeout.stop()

        if self._ws_client:
            self._ws_client.close()
            self._ws_client = None
        if self._ws_server:
            self._ws_server.close()
            self._ws_server = None

        self._kill_godot()

        if self._width > 0 and self._height > 0:
            ideal_w = self._width * CELL_PX + WALL_PX
            ideal_h = self._height * CELL_PX + WALL_PX
            self.setMinimumSize(ideal_w, ideal_h)
        self.update()

    def _kill_godot(self) -> None:
        proc = self._godot_process
        self._godot_process = None
        if proc and proc.state() != QProcess.ProcessState.NotRunning:
            proc.terminate()
            if not proc.waitForFinished(1500):
                proc.kill()
                proc.waitForFinished(3000)

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

        # Always keep the in-window map sized and repainted, even when Godot 3D is active.
        ideal_w = self._width * CELL_PX + WALL_PX
        ideal_h = self._height * CELL_PX + WALL_PX
        self.setMinimumSize(ideal_w, ideal_h)

        if self._godot_available:
            cells_data = [
                {
                    "row": cv.row, "col": cv.col, "kind": cv.kind,
                    "visible": cv.visible, "is_player": cv.is_player,
                    "has_gate": cv.has_gate, "solved": cv.solved,
                    "connections": list(cv.connections),
                }
                for cv in snapshot.cells
            ]
            self._send_to_godot({
                "type": "maze_update",
                "snapshot": {
                    "width": snapshot.width,
                    "height": snapshot.height,
                    "cells": cells_data,
                },
            })
            if self._godot_process is None:
                self._launch_godot()
        self.update()

    def highlight_player(self, pos: tuple[int, int]) -> None:
        self._player_pos = pos
        if self._godot_available:
            self._send_to_godot({
                "type": "highlight_player",
                "row": pos[0], "col": pos[1],
            })
        else:
            self.update()

    def set_view_direction(self, direction: str) -> None:
        """Set Godot first-person facing direction (N/S/E/W)."""
        d = (direction or "").strip().upper()
        if d not in {"N", "S", "E", "W"}:
            return
        if self._godot_available:
            self._send_to_godot({"type": "set_view_direction", "value": d})

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
        """Programmatic click — emits direction_clicked if adjacent to player."""
        if self._player_pos is None:
            return
        pr, pc = self._player_pos
        dr, dc = row - pr, col - pc
        direction_map = {(-1, 0): "N", (1, 0): "S", (0, -1): "W", (0, 1): "E"}
        direction = direction_map.get((dr, dc))
        if direction:
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
        painter.setBrush(COLOR_PLAYER)
        painter.setPen(Qt.PenStyle.NoPen)
        cx, cy = rect.center().x(), rect.center().y()
        r = min(rect.width(), rect.height()) * 0.3
        painter.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

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
        if self._godot_available:
            return
        x, y = event.position().x(), event.position().y()
        col = int(x // CELL_PX)
        row = int(y // CELL_PX)
        if 0 <= row < self._height and 0 <= col < self._width:
            self.click_cell(row, col)

    # -- Cleanup ------------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._is_closing = True
        if self._connect_timeout and self._connect_timeout.isActive():
            self._connect_timeout.stop()
        self._kill_godot()
        if self._ws_client:
            self._ws_client.close()
            self._ws_client = None
        if self._ws_server:
            self._ws_server.close()
            self._ws_server = None
        super().closeEvent(event)
