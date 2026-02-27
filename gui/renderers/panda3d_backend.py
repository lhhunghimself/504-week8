"""Panda3D in-process renderer backend.

Embeds a Panda3D window inside a QWidget, driven by a QTimer calling
taskMgr.step().  No subprocess, no WebSocket — everything runs in the
same process as the PyQt6 GUI.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

from gui.renderers.base_backend import BaseBackend

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

CELL_SIZE = 4.0
WALL_HEIGHT = 3.0
WALL_THICKNESS = 0.15
EYE_HEIGHT = 1.6
FPS_INTERVAL_MS = 16

_FACING_TO_H = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}
_H_TO_FACING = {0: "N", 90: "E", 180: "S", 270: "W"}

_KIND_COLORS = {
    "start": (0.06, 0.2, 0.37, 1),
    "exit": (0.32, 0.2, 0.51, 1),
    "normal": (0.09, 0.13, 0.24, 1),
}
_FOG_COLOR = (0.10, 0.10, 0.18, 1)
_GATE_COLOR = (0.96, 0.65, 0.14, 1)
_GATE_SOLVED_COLOR = (0.33, 0.75, 0.42, 1)
_WALL_COLOR = (0.25, 0.25, 0.35, 1)
_FLOOR_COLOR = (0.09, 0.13, 0.24, 1)
_CEILING_COLOR = (0.05, 0.05, 0.10, 1)


def _heading_for_facing(facing: str) -> float:
    return _FACING_TO_H.get(facing, 180.0)


def _facing_for_heading(heading: float) -> str:
    h = round(heading) % 360
    return _H_TO_FACING.get(h, "S")


class Panda3DBackend(BaseBackend):
    """In-process Panda3D renderer backend."""

    def __init__(self) -> None:
        super().__init__()
        self._base = None
        self._timer: QTimer | None = None
        self._parent_widget: QWidget | None = None
        self._started = False

        self._maze_root = None
        self._player_node = None
        self._current_snapshot: dict | None = None
        self._player_row = 0
        self._player_col = 0
        self._facing_h = 180.0
        self._facing_str = "S"
        self._is_moving = False

        self._key_map: dict[str, bool] = {}

    # -- BaseBackend --------------------------------------------------------

    def start(self, parent_widget: QWidget) -> None:
        if self._started:
            return
        self._parent_widget = parent_widget

        try:
            from direct.showbase.ShowBase import ShowBase
            from panda3d.core import WindowProperties, loadPrcFileData

            loadPrcFileData("", "window-type none")
            loadPrcFileData("", "audio-library-name null")

            self._base = ShowBase(windowType="none")

            props = WindowProperties()
            props.setParentWindow(int(parent_widget.winId()))
            props.setSize(parent_widget.width(), parent_widget.height())
            props.setOrigin(0, 0)
            self._base.openDefaultWindow(props=props)

            self._setup_lighting()
            self._setup_input()

            self._timer = QTimer()
            self._timer.timeout.connect(self._step)
            self._timer.start(FPS_INTERVAL_MS)

            self._started = True
            log.info("Panda3D backend started (size=%dx%d)",
                     parent_widget.width(), parent_widget.height())

        except Exception:
            log.exception("Failed to start Panda3D backend")
            self._base = None

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._base is not None:
            try:
                self._base.destroy()
            except Exception:
                log.exception("Error destroying Panda3D")
            self._base = None
        self._started = False
        self._maze_root = None
        self._player_node = None
        log.info("Panda3D backend stopped")

    def is_ready(self) -> bool:
        return self._started and self._base is not None

    def send_maze_update(self, snapshot_dict: dict) -> None:
        self._current_snapshot = snapshot_dict
        if not self._started:
            return
        self._rebuild_scene(snapshot_dict)

    def send_highlight_player(self, row: int, col: int) -> None:
        self._player_row = row
        self._player_col = col
        if self._player_node is not None:
            x, y = self._cell_center(row, col)
            self._player_node.setPos(x, y, EYE_HEIGHT)

    def send_view_direction(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d in _FACING_TO_H:
            self._facing_h = _heading_for_facing(d)
            self._facing_str = d
            if self._base is not None:
                self._base.cam.setH(self._facing_h)

    # -- Scene construction -------------------------------------------------

    def _setup_lighting(self) -> None:
        from panda3d.core import AmbientLight, DirectionalLight, LVector4

        ambient = AmbientLight("ambient")
        ambient.setColor(LVector4(0.35, 0.35, 0.4, 1))
        self._base.render.setLight(self._base.render.attachNewNode(ambient))

        sun = DirectionalLight("sun")
        sun.setColor(LVector4(0.7, 0.7, 0.65, 1))
        sun_np = self._base.render.attachNewNode(sun)
        sun_np.setHpr(45, -60, 0)
        self._base.render.setLight(sun_np)

        fill = DirectionalLight("fill")
        fill.setColor(LVector4(0.3, 0.3, 0.35, 1))
        fill_np = self._base.render.attachNewNode(fill)
        fill_np.setHpr(-135, -30, 0)
        self._base.render.setLight(fill_np)

    def _setup_input(self) -> None:
        for key, action in [
            ("w", "forward"), ("arrow_up", "forward"),
            ("s", "backward"), ("arrow_down", "backward"),
            ("q", "turn_left"), ("a", "turn_left"),
            ("e", "turn_right"), ("d", "turn_right"),
        ]:
            self._key_map[action] = False
            self._base.accept(key, self._set_key, [action, True])
            self._base.accept(f"{key}-up", self._set_key, [action, False])

    def _set_key(self, action: str, value: bool) -> None:
        was = self._key_map.get(action, False)
        self._key_map[action] = value
        if value and not was:
            self._handle_key_press(action)

    def _handle_key_press(self, action: str) -> None:
        if action == "turn_left":
            self._facing_h = (self._facing_h - 90) % 360
            new_facing = _facing_for_heading(self._facing_h)
            if self._base is not None:
                self._base.cam.setH(self._facing_h)
            if new_facing != self._facing_str:
                self._facing_str = new_facing
                self._emit_facing(new_facing)
        elif action == "turn_right":
            self._facing_h = (self._facing_h + 90) % 360
            new_facing = _facing_for_heading(self._facing_h)
            if self._base is not None:
                self._base.cam.setH(self._facing_h)
            if new_facing != self._facing_str:
                self._facing_str = new_facing
                self._emit_facing(new_facing)
        elif action == "forward":
            self._emit_direction(self._facing_str)
        elif action == "backward":
            opposites = {"N": "S", "S": "N", "E": "W", "W": "E"}
            self._emit_direction(opposites.get(self._facing_str, "S"))

    def _rebuild_scene(self, snapshot: dict) -> None:
        if self._base is None:
            return

        if self._maze_root is not None:
            self._maze_root.removeNode()

        self._maze_root = self._base.render.attachNewNode("maze_root")

        width = snapshot.get("width", 0)
        height = snapshot.get("height", 0)
        cells = snapshot.get("cells", [])

        cell_lookup: dict[tuple[int, int], dict] = {}
        for cell in cells:
            cell_lookup[(cell["row"], cell["col"])] = cell

        for cell in cells:
            row, col = cell["row"], cell["col"]
            self._build_cell_floor(cell, row, col)
            self._build_cell_ceiling(row, col)
            self._build_cell_walls(cell, row, col, width, height, cell_lookup)
            self._build_cell_markers(cell, row, col)

            if cell.get("is_player"):
                self._player_row = row
                self._player_col = col

        self._player_node = self._maze_root.attachNewNode("player")
        x, y = self._cell_center(self._player_row, self._player_col)
        self._player_node.setPos(x, y, EYE_HEIGHT)

        self._base.cam.reparentTo(self._player_node)
        self._base.cam.setPos(0, 0, 0)
        self._base.cam.setH(self._facing_h)
        self._base.cam.setP(0)

    def _cell_center(self, row: int, col: int) -> tuple[float, float]:
        x = col * CELL_SIZE + CELL_SIZE / 2
        y = -(row * CELL_SIZE + CELL_SIZE / 2)
        return x, y

    def _build_cell_floor(self, cell: dict, row: int, col: int) -> None:
        from panda3d.core import CardMaker, LVector4

        cm = CardMaker(f"floor_{row}_{col}")
        half = CELL_SIZE / 2
        cm.setFrame(-half, half, -half, half)

        cx, cy = self._cell_center(row, col)
        node = self._maze_root.attachNewNode(cm.generate())
        node.setP(-90)
        node.setPos(cx, cy, 0)

        if not cell.get("visible", False):
            color = _FOG_COLOR
        elif cell.get("has_gate") and not cell.get("solved"):
            color = _GATE_COLOR
        elif cell.get("has_gate") and cell.get("solved"):
            color = _GATE_SOLVED_COLOR
        else:
            kind = cell.get("kind", "normal")
            color = _KIND_COLORS.get(kind, _FLOOR_COLOR)

        node.setColor(LVector4(*color))

    def _build_cell_ceiling(self, row: int, col: int) -> None:
        from panda3d.core import CardMaker, LVector4

        cm = CardMaker(f"ceil_{row}_{col}")
        half = CELL_SIZE / 2
        cm.setFrame(-half, half, -half, half)

        cx, cy = self._cell_center(row, col)
        node = self._maze_root.attachNewNode(cm.generate())
        node.setP(90)
        node.setPos(cx, cy, WALL_HEIGHT)
        node.setColor(LVector4(*_CEILING_COLOR))

    def _build_cell_walls(
        self,
        cell: dict,
        row: int,
        col: int,
        width: int,
        height: int,
        cell_lookup: dict,
    ) -> None:
        connections = set(cell.get("connections", []))
        cx, cy = self._cell_center(row, col)
        half = CELL_SIZE / 2

        wall_specs = [
            ("N", (cx, cy + half, 0), (0, 0, 0)),
            ("S", (cx, cy - half, 0), (0, 180, 0)),
            ("E", (cx + half, cy, 0), (0, -90, 0)),
            ("W", (cx - half, cy, 0), (0, 90, 0)),
        ]

        for direction, pos, hpr in wall_specs:
            if direction not in connections:
                self._make_wall(pos, hpr)

    def _make_wall(self, pos: tuple, hpr: tuple) -> None:
        from panda3d.core import CardMaker, LVector4

        cm = CardMaker("wall")
        half_w = CELL_SIZE / 2
        cm.setFrame(-half_w, half_w, 0, WALL_HEIGHT)

        node = self._maze_root.attachNewNode(cm.generate())
        node.setPos(*pos)
        node.setH(hpr[1])
        node.setColor(LVector4(*_WALL_COLOR))
        node.setTwoSided(True)

    def _build_cell_markers(self, cell: dict, row: int, col: int) -> None:
        """Add floating markers for gates and exit."""
        if not cell.get("visible", False):
            return

        kind = cell.get("kind", "normal")
        cx, cy = self._cell_center(row, col)

        if kind == "exit":
            self._make_marker(cx, cy, 1.5, (0.0, 1.0, 0.25, 1.0), scale=0.6)
        if cell.get("has_gate") and not cell.get("solved"):
            self._make_marker(cx, cy, 2.0, _GATE_COLOR, scale=0.4)
        elif cell.get("has_gate") and cell.get("solved"):
            self._make_marker(cx, cy, 2.0, _GATE_SOLVED_COLOR, scale=0.4)

    def _make_marker(self, x: float, y: float, z: float, color: tuple, scale: float = 0.5) -> None:
        from panda3d.core import LVector4

        marker = self._base.loader.loadModel("models/box")
        marker.reparentTo(self._maze_root)
        marker.setPos(x, y, z)
        marker.setScale(scale)
        marker.setColor(LVector4(*color))

    # -- Render loop --------------------------------------------------------

    def _step(self) -> None:
        if self._base is None:
            return
        try:
            self._base.taskMgr.step()
        except Exception:
            log.exception("Panda3D step error")

    def _handle_resize(self) -> None:
        if self._base is None or self._parent_widget is None:
            return
        from panda3d.core import WindowProperties
        props = WindowProperties()
        props.setSize(self._parent_widget.width(), self._parent_widget.height())
        if self._base.win is not None:
            self._base.win.requestProperties(props)
