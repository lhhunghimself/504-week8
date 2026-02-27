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
EYE_HEIGHT = 1.6
FPS_INTERVAL_MS = 16

# Panda3D heading (H) uses +Y as forward (0°) and positive heading rotates left:
#   H=0   → +Y
#   H=90  → -X
#   H=180 → -Y
#   H=270 → +X
# Our maze uses:
#   N → +Y, E → +X, S → -Y, W → -X
_FACING_TO_H = {"N": 0.0, "E": 270.0, "S": 180.0, "W": 90.0}
_H_TO_FACING = {0: "N", 90: "W", 180: "S", 270: "E"}

_KIND_COLORS = {
    "start": (0.06, 0.2, 0.37, 1),
    "exit": (0.32, 0.2, 0.51, 1),
    "normal": (0.09, 0.13, 0.24, 1),
}
_FOG_COLOR = (0.10, 0.10, 0.18, 1)
_GATE_COLOR = (0.96, 0.65, 0.14, 1)
_GATE_SOLVED_COLOR = (0.33, 0.75, 0.42, 1)
_WALL_COLOR = (0.85, 0.82, 1.0, 1)   # light tint: texture provides dark tones
_FLOOR_COLOR = (0.09, 0.13, 0.24, 1)
_CEILING_COLOR = (0.55, 0.40, 0.70, 1)  # visible ceiling tint


def _make_brick_texture(size: int = 128):
    """Generate a tileable stone-brick texture procedurally."""
    from panda3d.core import PNMImage, Texture
    img = PNMImage(size, size)
    bw = size // 4
    bh = size // 8
    mortar = max(2, size // 40)
    for y in range(size):
        row = y // bh
        offset = (bw // 2) * (row % 2)
        for x in range(size):
            bx = (x + offset) % size
            in_mortar_x = (bx % bw) < mortar
            in_mortar_y = (y % bh) < mortar
            if in_mortar_x or in_mortar_y:
                img.setXelA(x, y, 0.42, 0.39, 0.50, 1.0)
            else:
                noise = (((x * 7 + y * 13) ^ (x * 3)) % 31) / 31.0 * 0.18
                img.setXelA(x, y, 0.62 + noise, 0.57 + noise, 0.72 + noise, 1.0)
    tex = Texture("wall_brick")
    tex.load(img)
    tex.setWrapU(Texture.WM_repeat)
    tex.setWrapV(Texture.WM_repeat)
    tex.setMagfilter(Texture.FT_linear)
    tex.setMinfilter(Texture.FT_linear_mipmap_linear)
    return tex


def _make_floor_texture(size: int = 128):
    """Generate a tileable stone-tile floor texture procedurally."""
    from panda3d.core import PNMImage, Texture
    img = PNMImage(size, size)
    tile = size // 4
    grout = max(2, size // 32)
    for y in range(size):
        for x in range(size):
            if (x % tile) < grout or (y % tile) < grout:
                img.setXelA(x, y, 0.06, 0.08, 0.14, 1.0)
            else:
                noise = (((x * 5 + y * 11) ^ y) % 23) / 23.0 * 0.06
                img.setXelA(x, y, 0.11 + noise, 0.16 + noise, 0.28 + noise, 1.0)
    tex = Texture("floor_tile")
    tex.load(img)
    tex.setWrapU(Texture.WM_repeat)
    tex.setWrapV(Texture.WM_repeat)
    tex.setMagfilter(Texture.FT_linear)
    tex.setMinfilter(Texture.FT_linear_mipmap_linear)
    return tex


def _make_ceiling_texture(size: int = 64):
    """Generate a plain dark stone ceiling texture."""
    from panda3d.core import PNMImage, Texture
    img = PNMImage(size, size)
    for y in range(size):
        for x in range(size):
            noise = (((x * 3 + y * 7) ^ x) % 19) / 19.0 * 0.04
            img.setXelA(x, y, 0.08 + noise, 0.06 + noise, 0.12 + noise, 1.0)
    tex = Texture("ceiling_stone")
    tex.load(img)
    tex.setWrapU(Texture.WM_repeat)
    tex.setWrapV(Texture.WM_repeat)
    tex.setMagfilter(Texture.FT_linear)
    tex.setMinfilter(Texture.FT_linear_mipmap_linear)
    return tex


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
        self._minimap_root = None
        self._minimap_cells: dict[tuple[int, int], object] = {}
        self._minimap_player = None
        self._minimap_arrow = None
        self._snapshot_width = 0
        self._snapshot_height = 0

        # Procedural textures — generated once after Panda3D starts.
        self._tex_wall = None
        self._tex_floor = None
        self._tex_ceiling = None
        self._player_light = None

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

            pix_w, pix_h, dpr = self._host_pixel_size(parent_widget)
            props = WindowProperties()
            props.setParentWindow(int(parent_widget.winId()))
            # Qt widget sizes are in device-independent pixels; Panda3D expects
            # physical pixels when embedding into a native X11 window.
            props.setSize(pix_w, pix_h)
            props.setOrigin(0, 0)
            self._base.openDefaultWindow(props=props)

            # Dark background matching the maze ceiling/fog color.
            self._base.win.setClearColor((0.06, 0.05, 0.10, 1))

            self._base.camLens.setFov(75)
            self._setup_lighting()
            self._setup_input()
            self._setup_textures()

            self._timer = QTimer()
            self._timer.timeout.connect(self._step)
            self._timer.start(FPS_INTERVAL_MS)

            self._started = True
            # If snapshots arrived before start(), render immediately after boot.
            if self._current_snapshot:
                self._rebuild_scene(self._current_snapshot)
            log.info(
                "Panda3D backend started (logical=%dx%d px=%dx%d dpr=%.2f)",
                parent_widget.width(),
                parent_widget.height(),
                pix_w,
                pix_h,
                dpr,
            )

        except Exception:
            log.exception("Failed to start Panda3D backend")
            self._base = None

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._base is not None:
            try:
                # Close the graphics window before destroying ShowBase to avoid
                # GLXBadDrawable errors on X11 when the parent Qt widget is
                # already unmapped during application shutdown.
                if self._base.win is not None:
                    self._base.win.setActive(False)
                    try:
                        self._base.graphicsEngine.removeWindow(self._base.win)
                    except Exception:
                        pass
                self._base.destroy()
            except Exception:
                log.debug("Error destroying Panda3D (expected on some X11 configs)")
            self._base = None
        self._started = False
        self._maze_root = None
        self._player_node = None
        self._tex_wall = None
        self._tex_floor = None
        self._tex_ceiling = None
        log.info("Panda3D backend stopped")

    def is_ready(self) -> bool:
        return self._started and self._base is not None

    def _host_pixel_size(self, widget: QWidget) -> tuple[int, int, float]:
        """Return (pixel_w, pixel_h, dpr) for a Qt widget."""
        dpr = 1.0
        try:
            dpr = float(widget.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        w = max(1, int(round(widget.width() * dpr)))
        h = max(1, int(round(widget.height() * dpr)))
        return w, h, dpr

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
        self._update_minimap_player()

    def inject_key(self, panda_key: str, *, pressed: bool) -> None:
        """Forward a Qt key event into Panda3D's messenger by key name."""
        if self._base is None:
            return
        event_name = panda_key if pressed else f"{panda_key}-up"
        self._base.messenger.send(event_name, [])

    def send_view_direction(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d in _FACING_TO_H:
            self._facing_h = _heading_for_facing(d)
            self._facing_str = d
            if self._base is not None:
                self._base.cam.setH(self._facing_h)
            self._update_minimap_player()

    # -- Scene construction -------------------------------------------------

    def _setup_lighting(self) -> None:
        from panda3d.core import AmbientLight, PointLight, LVector4, LPoint3f, LColor

        # Moderate ambient so distant walls aren't pitch black.
        ambient = AmbientLight("ambient")
        ambient.setColor(LVector4(0.25, 0.22, 0.30, 1))
        self._base.render.setLight(self._base.render.attachNewNode(ambient))

        # Player-attached point light: illuminates nearby walls like a torch.
        # Intensity 2.5, gentle falloff so walls 2-8 units away are well-lit.
        self._player_light = PointLight("player_light")
        self._player_light.setColor(LColor(2.5, 2.4, 2.2, 1))
        self._player_light.setAttenuation((0.3, 0.0, 0.003))
        player_light_np = self._base.cam.attachNewNode(self._player_light)
        player_light_np.setPos(0, 0, 0)
        self._base.render.setLight(player_light_np)

    def _setup_input(self) -> None:
        for key, action in [
            ("w", "forward"), ("arrow_up", "forward"),
            ("s", "backward"), ("arrow_down", "backward"),
            ("q", "turn_left"), ("a", "turn_left"),
            ("e", "turn_right"), ("d", "turn_right"),
            ("arrow_left", "turn_left"), ("arrow_right", "turn_right"),
        ]:
            self._key_map[action] = False
            self._base.accept(key, self._set_key, [action, True])
            self._base.accept(f"{key}-up", self._set_key, [action, False])

    def _setup_textures(self) -> None:
        """Generate procedural wall/floor/ceiling textures once after startup."""
        try:
            self._tex_wall = _make_brick_texture()
            self._tex_floor = _make_floor_texture()
            self._tex_ceiling = _make_ceiling_texture()
            log.debug("Procedural textures generated")
        except Exception:
            log.warning("Texture generation failed, falling back to flat shading")
            self._tex_wall = None
            self._tex_floor = None
            self._tex_ceiling = None

    def _set_key(self, action: str, value: bool) -> None:
        was = self._key_map.get(action, False)
        self._key_map[action] = value
        if value and not was:
            self._handle_key_press(action)

    def _handle_key_press(self, action: str) -> None:
        if action == "turn_left":
            self._facing_h = (self._facing_h + 90) % 360
            new_facing = _facing_for_heading(self._facing_h)
            if self._base is not None:
                self._base.cam.setH(self._facing_h)
            if new_facing != self._facing_str:
                self._facing_str = new_facing
                self._emit_facing(new_facing)
            self._update_minimap_player()
        elif action == "turn_right":
            self._facing_h = (self._facing_h - 90) % 360
            new_facing = _facing_for_heading(self._facing_h)
            if self._base is not None:
                self._base.cam.setH(self._facing_h)
            if new_facing != self._facing_str:
                self._facing_str = new_facing
                self._emit_facing(new_facing)
            self._update_minimap_player()
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

        self._snapshot_width = width
        self._snapshot_height = height
        self._rebuild_minimap(snapshot)

    def _cell_center(self, row: int, col: int) -> tuple[float, float]:
        x = col * CELL_SIZE + CELL_SIZE / 2
        y = -(row * CELL_SIZE + CELL_SIZE / 2)
        return x, y

    def _build_cell_floor(self, cell: dict, row: int, col: int) -> None:
        from panda3d.core import CardMaker, LVector4, Point2

        cm = CardMaker(f"floor_{row}_{col}")
        half = CELL_SIZE / 2
        cm.setFrame(-half, half, -half, half)
        cm.setUvRange(Point2(0, 0), Point2(1, 1))

        cx, cy = self._cell_center(row, col)
        node = self._maze_root.attachNewNode(cm.generate())
        node.setP(-90)
        node.setPos(cx, cy, 0)

        if not cell.get("visible", False):
            color = _FOG_COLOR
            node.setColor(LVector4(*color))
        elif cell.get("has_gate") and not cell.get("solved"):
            color = _GATE_COLOR
            node.setColor(LVector4(*color))
        elif cell.get("has_gate") and cell.get("solved"):
            color = _GATE_SOLVED_COLOR
            node.setColor(LVector4(*color))
        else:
            kind = cell.get("kind", "normal")
            tint = _KIND_COLORS.get(kind, _FLOOR_COLOR)
            if self._tex_floor is not None:
                node.setTexture(self._tex_floor)
                node.setColorScale(LVector4(*tint))
            else:
                node.setColor(LVector4(*tint))

    def _build_cell_ceiling(self, row: int, col: int) -> None:
        from panda3d.core import CardMaker, LVector4, Point2

        cm = CardMaker(f"ceil_{row}_{col}")
        half = CELL_SIZE / 2
        cm.setFrame(-half, half, -half, half)
        cm.setUvRange(Point2(0, 0), Point2(1, 1))

        cx, cy = self._cell_center(row, col)
        node = self._maze_root.attachNewNode(cm.generate())
        node.setP(90)
        node.setPos(cx, cy, WALL_HEIGHT)

        if self._tex_ceiling is not None:
            node.setTexture(self._tex_ceiling)
            node.setColorScale(LVector4(*_CEILING_COLOR))
        else:
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

        # HPR so each card's normal faces INTO the cell (toward the player).
        # CardMaker default normal is +Y. setH rotates around Z:
        #   N wall (at +Y edge): normal must point -Y → H=180
        #   S wall (at -Y edge): normal must point +Y → H=0
        #   E wall (at +X edge): normal must point -X → H=-90 (270)
        #   W wall (at -X edge): normal must point +X → H=90
        wall_specs = [
            ("N", (cx, cy + half, 0), (0, 180, 0)),
            ("S", (cx, cy - half, 0), (0, 0, 0)),
            ("E", (cx + half, cy, 0), (0, -90, 0)),
            ("W", (cx - half, cy, 0), (0, 90, 0)),
        ]

        for direction, pos, hpr in wall_specs:
            if direction not in connections:
                self._make_wall(pos, hpr)

    def _make_wall(self, pos: tuple, hpr: tuple) -> None:
        from panda3d.core import CardMaker, LVector4, Point2

        cm = CardMaker("wall")
        half_w = CELL_SIZE / 2
        cm.setFrame(-half_w, half_w, 0, WALL_HEIGHT)
        # UV: tile 1× horizontally across the cell width, 1× vertically for wall height.
        cm.setUvRange(Point2(0, 0), Point2(1, 1))

        node = self._maze_root.attachNewNode(cm.generate())
        node.setPos(*pos)
        node.setH(hpr[1])
        # Single-sided so point-light normal calculations work correctly.

        if self._tex_wall is not None:
            node.setTexture(self._tex_wall)
            # setColorScale tints the texture without replacing it.
            node.setColorScale(LVector4(*_WALL_COLOR))
        else:
            node.setColor(LVector4(*_WALL_COLOR))

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

    # -- Minimap overlay (2D HUD) -------------------------------------------

    def _rebuild_minimap(self, snapshot: dict) -> None:
        """Build a 2D minimap overlay in the top-right corner of the viewport."""
        if self._base is None:
            return
        from panda3d.core import CardMaker, LVector4, TextNode

        if self._minimap_root is not None:
            self._minimap_root.removeNode()
        self._minimap_cells.clear()

        self._minimap_root = self._base.aspect2d.attachNewNode("minimap")

        width = snapshot.get("width", 0)
        height = snapshot.get("height", 0)
        cells = snapshot.get("cells", [])
        if width == 0 or height == 0:
            return

        cell_sz = min(0.08, 0.4 / max(width, height))
        gap = cell_sz * 0.1
        total_w = width * (cell_sz + gap) - gap
        total_h = height * (cell_sz + gap) - gap

        anchor_x = self._base.getAspectRatio() - total_w - 0.05
        anchor_y = 1.0 - 0.05

        bg_cm = CardMaker("minimap_bg")
        pad = cell_sz * 0.3
        bg_cm.setFrame(-pad, total_w + pad, -(total_h + pad), pad)
        bg_node = self._minimap_root.attachNewNode(bg_cm.generate())
        bg_node.setPos(anchor_x, 0, anchor_y)
        bg_node.setColor(LVector4(0.0, 0.0, 0.0, 0.6))
        bg_node.setTransparency(1)

        for cell in cells:
            row, col = cell["row"], cell["col"]
            x = anchor_x + col * (cell_sz + gap)
            z = anchor_y - row * (cell_sz + gap)

            cm = CardMaker(f"mm_{row}_{col}")
            cm.setFrame(0, cell_sz, -cell_sz, 0)
            node = self._minimap_root.attachNewNode(cm.generate())
            node.setPos(x, 0, z)

            color = self._minimap_cell_color(cell)
            node.setColor(LVector4(*color))
            self._minimap_cells[(row, col)] = node

            conns = set(cell.get("connections", []))
            if cell.get("visible"):
                self._draw_minimap_connections(conns, x, z, cell_sz, gap)

        self._update_minimap_player()

    def _minimap_cell_color(self, cell: dict) -> tuple:
        if not cell.get("visible", False):
            return (0.10, 0.10, 0.18, 0.8)
        if cell.get("is_player"):
            return (0.91, 0.27, 0.37, 1.0)
        if cell.get("has_gate") and not cell.get("solved"):
            return _GATE_COLOR
        if cell.get("has_gate") and cell.get("solved"):
            return _GATE_SOLVED_COLOR
        kind = cell.get("kind", "normal")
        if kind == "start":
            return (0.06, 0.2, 0.37, 1.0)
        if kind == "exit":
            return (0.32, 0.2, 0.51, 1.0)
        return (0.09, 0.13, 0.24, 1.0)

    def _draw_minimap_connections(
        self, conns: set, x: float, z: float, cell_sz: float, gap: float,
    ) -> None:
        from panda3d.core import CardMaker, LVector4

        conn_color = LVector4(0.0, 1.0, 0.25, 0.7)
        line_w = cell_sz * 0.15

        for d in conns:
            cm = CardMaker("conn")
            if d == "E":
                cm.setFrame(cell_sz, cell_sz + gap, -cell_sz / 2 - line_w / 2, -cell_sz / 2 + line_w / 2)
            elif d == "S":
                cm.setFrame(cell_sz / 2 - line_w / 2, cell_sz / 2 + line_w / 2, -cell_sz - gap, -cell_sz)
            else:
                continue
            node = self._minimap_root.attachNewNode(cm.generate())
            node.setPos(x, 0, z)
            node.setColor(conn_color)
            node.setTransparency(1)

    def _update_minimap_player(self) -> None:
        """Refresh the player arrow indicator on the minimap."""
        if self._minimap_root is None or self._base is None:
            return
        from panda3d.core import CardMaker, LVector4

        if self._minimap_arrow is not None:
            self._minimap_arrow.removeNode()
            self._minimap_arrow = None

        cell_node = self._minimap_cells.get((self._player_row, self._player_col))
        if cell_node is None:
            return

        width = self._snapshot_width
        height = self._snapshot_height
        if width == 0 or height == 0:
            return

        cell_sz = min(0.08, 0.4 / max(width, height))

        arrow = self._minimap_root.attachNewNode("mm_arrow")
        cm = CardMaker("arrow_body")
        half = cell_sz * 0.15
        length = cell_sz * 0.35

        facing_offsets = {
            "N": (0, length), "S": (0, -length), "E": (length, 0), "W": (-length, 0),
        }
        dx, dz = facing_offsets.get(self._facing_str, (0, 0))

        cm.setFrame(-half, half, -half, half)
        dot = arrow.attachNewNode(cm.generate())
        x = cell_node.getX() + cell_sz / 2 + dx
        z = cell_node.getZ() - cell_sz / 2 + dz
        dot.setPos(x, 0, z)
        dot.setColor(LVector4(1.0, 1.0, 1.0, 1.0))

        self._minimap_arrow = arrow

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
        if self._base.win is None:
            return
        w, h, _dpr = self._host_pixel_size(self._parent_widget)
        # Skip if already the right size.
        if self._base.win.getXSize() == w and self._base.win.getYSize() == h:
            return
        from panda3d.core import WindowProperties
        props = WindowProperties()
        props.setSize(w, h)
        self._base.win.requestProperties(props)
        # Flush the resize by stepping the render loop immediately — Panda3D
        # processes window property changes during taskMgr.step(), not instantly.
        for _ in range(3):
            self._base.taskMgr.step()
