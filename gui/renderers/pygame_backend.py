"""Pygame raycaster renderer backend.

Renders to an off-screen ``pygame.Surface``, converts each frame to a
``QImage``, and paints it into a ``PygameViewport`` widget via ``QPainter``.
No native Pygame window is opened -- the display lives entirely within the
Qt widget hierarchy.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import pygame
from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QWidget

from gui.renderers.base_backend import BaseBackend
from gui.renderers.raycaster import (
    Grid,
    angle_for_facing,
    build_grid,
    facing_for_angle,
    render_frame,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

FPS_INTERVAL_MS = 16  # ~60 fps

_KEY_TO_ACTION: dict[str, str] = {
    "w": "forward",
    "arrow_up": "forward",
    "s": "backward",
    "arrow_down": "backward",
    "a": "turn_left",
    "q": "turn_left",
    "arrow_left": "turn_left",
    "d": "turn_right",
    "e": "turn_right",
    "arrow_right": "turn_right",
}

_HALF_PI = math.pi / 2
_TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# PygameViewport -- QWidget that paints the backend's current QImage
# ---------------------------------------------------------------------------

class PygameViewport(QWidget):
    """Host widget that blits the raycaster frame as a ``QImage``."""

    def __init__(self, backend: PygameBackend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        qimg = self._backend._current_qimage
        if qimg is None or qimg.isNull():
            return
        painter = QPainter(self)
        painter.drawImage(
            QRectF(0, 0, self.width(), self.height()),
            qimg,
        )
        painter.end()


# ---------------------------------------------------------------------------
# PygameBackend
# ---------------------------------------------------------------------------

class PygameBackend(BaseBackend):
    """Off-screen Pygame raycaster implementing ``BaseBackend``."""

    def __init__(self) -> None:
        super().__init__()
        self._viewport: QWidget | None = None
        self._timer: QTimer | None = None
        self._started = False

        self._surface: pygame.Surface | None = None
        self._width = 1
        self._height = 1

        self._grid: Grid | None = None
        self._current_snapshot: dict | None = None
        self._player_x = 0.5
        self._player_y = 0.5
        self._player_angle = angle_for_facing("S")
        self._facing_str = "S"

        # Safe buffer: keeps the bytes alive while QImage references them.
        self._frame_data: bytes = b""
        self._current_qimage: QImage | None = None

        self._pygame_inited = False

    # -- BaseBackend lifecycle -----------------------------------------------

    def start(self, parent_widget: QWidget) -> None:
        if self._started:
            return
        self._viewport = parent_widget

        if not self._pygame_inited:
            pygame.init()
            self._pygame_inited = True

        w, h, dpr = self._host_pixel_size(parent_widget)
        self._width = max(1, w)
        self._height = max(1, h)
        self._surface = pygame.Surface((self._width, self._height))

        self._timer = QTimer()
        self._timer.timeout.connect(self._render_tick)
        self._timer.start(FPS_INTERVAL_MS)

        self._started = True

        if self._current_snapshot is not None:
            self._grid = build_grid(self._current_snapshot)
            self._sync_player_from_snapshot(self._current_snapshot)

        log.info(
            "Pygame backend started (logical=%dx%d, px=%dx%d, dpr=%.2f)",
            parent_widget.width(), parent_widget.height(), w, h, dpr,
        )

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._surface = None
        self._viewport = None
        self._current_qimage = None
        self._frame_data = b""
        self._started = False
        if self._pygame_inited:
            pygame.quit()
            self._pygame_inited = False
        log.info("Pygame backend stopped")

    def is_ready(self) -> bool:
        return self._started and self._surface is not None

    # -- Data input ----------------------------------------------------------

    def send_maze_update(self, snapshot_dict: dict) -> None:
        self._current_snapshot = snapshot_dict
        self._grid = build_grid(snapshot_dict)
        self._sync_player_from_snapshot(snapshot_dict)
        if not self._started:
            return

    def send_highlight_player(self, row: int, col: int) -> None:
        self._player_x = col + 0.5
        self._player_y = row + 0.5

    def send_view_direction(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d in ("N", "S", "E", "W"):
            self._player_angle = angle_for_facing(d)
            if d != self._facing_str:
                self._facing_str = d
                self._emit_facing(d)

    # -- Key injection -------------------------------------------------------

    def inject_key(self, key_name: str, *, pressed: bool) -> None:
        if not pressed:
            return
        action = _KEY_TO_ACTION.get(key_name)
        if action is None:
            return
        self._handle_action(action)

    def _handle_action(self, action: str) -> None:
        if action == "turn_left":
            self._player_angle = (self._player_angle + _HALF_PI) % _TWO_PI
            new_f = facing_for_angle(self._player_angle)
            if new_f != self._facing_str:
                self._facing_str = new_f
                self._emit_facing(new_f)
        elif action == "turn_right":
            self._player_angle = (self._player_angle - _HALF_PI) % _TWO_PI
            new_f = facing_for_angle(self._player_angle)
            if new_f != self._facing_str:
                self._facing_str = new_f
                self._emit_facing(new_f)
        elif action == "forward":
            self._emit_direction(self._facing_str)
        elif action == "backward":
            opp = {"N": "S", "S": "N", "E": "W", "W": "E"}
            self._emit_direction(opp.get(self._facing_str, "S"))

    # -- Render loop ---------------------------------------------------------

    def _render_tick(self) -> None:
        if self._surface is None or self._grid is None:
            return

        # Auto-resize if the viewport changed size.
        if self._viewport is not None:
            w, h, _ = self._host_pixel_size(self._viewport)
            w, h = max(1, w), max(1, h)
            if self._surface.get_width() != w or self._surface.get_height() != h:
                self._surface = pygame.Surface((w, h))
                self._width = w
                self._height = h

        w, h = self._surface.get_size()
        render_frame(
            self._surface, self._grid,
            self._player_x, self._player_y, self._player_angle,
            w, h,
        )

        self._frame_data = pygame.image.tobytes(self._surface, "RGB")
        self._current_qimage = QImage(
            self._frame_data, w, h, w * 3,
            QImage.Format.Format_RGB888,
        )

        if self._viewport is not None:
            self._viewport.update()

    # -- DPR helper ----------------------------------------------------------

    @staticmethod
    def _host_pixel_size(widget: QWidget) -> tuple[int, int, float]:
        dpr = 1.0
        try:
            dpr = float(widget.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        w = max(1, int(round(widget.width() * dpr)))
        h = max(1, int(round(widget.height() * dpr)))
        return w, h, dpr

    def _handle_resize(self) -> None:
        """Recreate the off-screen surface at the current viewport size."""
        if self._viewport is None or self._surface is None:
            return
        w, h, _ = self._host_pixel_size(self._viewport)
        w, h = max(1, w), max(1, h)
        if self._surface.get_width() == w and self._surface.get_height() == h:
            return
        self._surface = pygame.Surface((w, h))
        self._width = w
        self._height = h

    def _sync_player_from_snapshot(self, snapshot_dict: dict) -> None:
        """Align camera/player position from a snapshot's ``is_player`` cell."""
        for cell in snapshot_dict.get("cells", []):
            if cell.get("is_player"):
                self._player_x = float(cell.get("col", 0)) + 0.5
                self._player_y = float(cell.get("row", 0)) + 0.5
                return
