"""QPainter pre-rendered dungeon-crawler backend.

Pre-computes a QPixmap for every (row, col, facing) combination when a maze
snapshot arrives.  At display time the viewport just blits the cached pixmap --
zero per-frame computation.

Visual style: classic first-person dungeon crawler (Eye of the Beholder /
Wizardry) with perspective-correct wall trapezoids, depth fog, and cell-type
colour coding.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QWidget

from gui.renderers.base_backend import BaseBackend

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_COL_FLOOR = QColor("#0d1117")
_COL_CEILING = QColor("#1a1a2e")
_COL_FOG = QColor("#1a1a2e")

_COL_WALL_FRONT = QColor(30, 46, 30)
_COL_WALL_SIDE = QColor(22, 33, 62)
_COL_GATE = QColor("#f5a623")
_COL_GATE_SOLVED = QColor("#53bf6a")
_COL_START = QColor("#0f3460")
_COL_EXIT = QColor("#533483")

# Depth fog multipliers (0=near, 1=mid, 2=far)
_FOG_ALPHA = [0, 60, 130]

# ---------------------------------------------------------------------------
# Procedural textures (64x64, cached on first use)
# ---------------------------------------------------------------------------

_TEX_SIZE = 64
_texture_cache: dict[str, QPixmap] = {}


def _get_texture(name: str) -> QPixmap:
    if name not in _texture_cache:
        _texture_cache[name] = _TEXTURE_GENERATORS[name]()
    return _texture_cache[name]


# Hash-based per-pixel noise (deterministic, no imports needed).
def _pnoise(x: int, y: int, seed: int = 0) -> int:
    """Return pseudo-random 0-255 from coordinates.  Fast integer hash."""
    n = x + y * 57 + seed * 131
    n = (n << 13) ^ n
    return ((n * (n * n * 15731 + 789221) + 1376312589) & 0x7FFFFFFF) % 256


def _clamp(v: int, lo: int = 0, hi: int = 255) -> int:
    return max(lo, min(hi, v))


# ---- Doom-palette colour ramps ----
# Derived from the actual Doom PLAYPAL brown, gray, and tan ramps.
_BROWN_RAMP = [
    (56, 40, 24), (68, 48, 28), (80, 56, 36), (92, 64, 44),
    (104, 76, 52), (116, 84, 56), (128, 96, 64), (140, 104, 68),
    (156, 116, 80), (168, 128, 88), (180, 140, 100), (196, 156, 112),
    (212, 172, 128), (224, 188, 140), (236, 200, 152), (244, 216, 168),
]
_GRAY_RAMP = [
    (28, 28, 32), (36, 36, 40), (44, 44, 48), (52, 52, 56),
    (64, 64, 68), (76, 76, 80), (88, 88, 92), (100, 100, 104),
    (112, 112, 116), (124, 124, 128), (136, 136, 140), (148, 148, 152),
    (160, 160, 164), (176, 176, 178), (192, 192, 194), (208, 208, 210),
]


def _gen_stone_wall() -> QPixmap:
    """Doom BROWN1-style running-bond brickwork with per-brick variation."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    mortar_r, mortar_g, mortar_b = 30, 24, 18
    brick_h = 8
    brick_w = 16
    mortar_w = 1

    for py in range(S):
        brick_row = py // brick_h
        y_in_brick = py % brick_h
        is_h_mortar = y_in_brick < mortar_w
        x_offset = (brick_w // 2) if brick_row % 2 else 0

        for px in range(S):
            ax = (px + x_offset) % S
            brick_col = ax // brick_w
            x_in_brick = ax % brick_w
            is_v_mortar = x_in_brick < mortar_w

            if is_h_mortar or is_v_mortar:
                n = _pnoise(px, py, 7) // 16
                r = _clamp(mortar_r + n - 8)
                g = _clamp(mortar_g + n - 8)
                b = _clamp(mortar_b + n - 8)
            else:
                seed = brick_row * 7 + brick_col * 13
                ramp_idx = 3 + (_pnoise(brick_col, brick_row, 99) % 6)
                base_r, base_g, base_b = _BROWN_RAMP[ramp_idx]
                n = _pnoise(px, py, seed)
                variation = (n % 21) - 10
                edge_dark = 0
                if y_in_brick == mortar_w or x_in_brick == mortar_w:
                    edge_dark = 12
                if y_in_brick == brick_h - 1 or x_in_brick == brick_w - 1:
                    edge_dark = -8
                stain = -16 if _pnoise(px, py, 42) > 240 else 0
                r = _clamp(base_r + variation - edge_dark + stain)
                g = _clamp(base_g + variation - edge_dark + stain)
                b = _clamp(base_b + variation - edge_dark + stain)

            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


def _gen_stone_floor() -> QPixmap:
    """Doom FLAT5_4-style dark stone flagstones with cracks."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    flag_size = 16
    mortar_w = 1

    for py in range(S):
        flag_row = py // flag_size
        y_in = py % flag_size
        is_h_mortar = y_in < mortar_w

        for px in range(S):
            flag_col = px // flag_size
            x_in = px % flag_size
            is_v_mortar = x_in < mortar_w

            if is_h_mortar or is_v_mortar:
                n = _pnoise(px, py, 3) // 20
                r = g = b = _clamp(22 + n)
            else:
                seed = flag_row * 11 + flag_col * 23
                ramp_idx = 2 + (_pnoise(flag_col, flag_row, 77) % 4)
                base_r, base_g, base_b = _GRAY_RAMP[ramp_idx]
                n = _pnoise(px, py, seed)
                variation = (n % 17) - 8
                edge_hi = 6 if (y_in == mortar_w or x_in == mortar_w) else 0
                edge_lo = -4 if (y_in == flag_size - 1 or x_in == flag_size - 1) else 0
                crack = -20 if _pnoise(px, py, 200) > 248 else 0
                v = variation + edge_hi + edge_lo + crack
                r = _clamp(base_r + v)
                g = _clamp(base_g + v)
                b = _clamp(base_b + v)

            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


def _gen_ceiling() -> QPixmap:
    """Doom CEIL3_3-style rough dark rock ceiling."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    for py in range(S):
        for px in range(S):
            n1 = _pnoise(px, py, 0)
            n2 = _pnoise(px // 2, py // 2, 50)
            v = (n1 + n2) // 2
            idx = v // 32
            base_r, base_g, base_b = _GRAY_RAMP[min(idx + 1, 5)]
            detail = (v % 13) - 6
            r = _clamp(base_r + detail - 12)
            g = _clamp(base_g + detail - 12)
            b = _clamp(base_b + detail - 8)
            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


def _gen_gate_barrier() -> QPixmap:
    """FIREBLU-inspired orange energy wall with vertical bars and glow."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    for py in range(S):
        for px in range(S):
            bar_phase = abs((px % 16) - 8)
            scan = abs((py % 8) - 4)
            n = _pnoise(px, py, 33)
            glow = max(0, 8 - bar_phase) * 20 + max(0, 4 - scan) * 12
            base_r = _clamp(40 + glow + (n % 20))
            base_g = _clamp(16 + glow // 3 + (n % 10))
            base_b = _clamp(4 + (n % 8))
            hot = 1 if bar_phase < 2 and scan < 2 else 0
            r = _clamp(base_r + hot * 80)
            g = _clamp(base_g + hot * 50)
            b = _clamp(base_b + hot * 10)
            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


def _gen_gate_solved() -> QPixmap:
    """Green translucent energy barrier — solved gate variant."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    for py in range(S):
        for px in range(S):
            bar_phase = abs((px % 16) - 8)
            scan = abs((py % 8) - 4)
            n = _pnoise(px, py, 55)
            glow = max(0, 8 - bar_phase) * 14 + max(0, 4 - scan) * 10
            base_r = _clamp(6 + (n % 10))
            base_g = _clamp(32 + glow + (n % 20))
            base_b = _clamp(12 + glow // 4 + (n % 10))
            hot = 1 if bar_phase < 2 and scan < 2 else 0
            r = _clamp(base_r + hot * 20)
            g = _clamp(base_g + hot * 80)
            b = _clamp(base_b + hot * 30)
            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


def _gen_start_panel() -> QPixmap:
    """Doom COMPTILE-style blue-gray tech panel with UAC-like trim."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    panel = 32
    trim = 2
    for py in range(S):
        py_in = py % panel
        for px in range(S):
            px_in = px % panel
            is_trim = (
                py_in < trim or py_in >= panel - trim
                or px_in < trim or px_in >= panel - trim
            )
            n = _pnoise(px, py, 17)
            if is_trim:
                r = _clamp(20 + (n % 12))
                g = _clamp(40 + (n % 16))
                b = _clamp(100 + (n % 24))
            else:
                n2 = _pnoise(px // 2, py // 2, 88)
                v = (n + n2) // 2
                circuit = 1 if (px_in == 16 or py_in == 16) and n > 128 else 0
                r = _clamp(14 + (v % 10) + circuit * 8)
                g = _clamp(22 + (v % 14) + circuit * 16)
                b = _clamp(48 + (v % 20) + circuit * 40)
            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


def _gen_exit_portal() -> QPixmap:
    """Doom SKINFACE-inspired purple organic portal texture."""
    S = _TEX_SIZE
    pm = QPixmap(S, S)
    img = pm.toImage()

    cx, cy = S // 2, S // 2
    max_dist = math.sqrt(cx * cx + cy * cy)

    for py in range(S):
        for px in range(S):
            dx, dy = px - cx, py - cy
            dist = math.sqrt(dx * dx + dy * dy)
            ring = math.sin(dist * 0.8) * 0.5 + 0.5
            norm_d = dist / max_dist
            n = _pnoise(px, py, 77)
            center_glow = max(0.0, 1.0 - norm_d * 1.4)

            r = _clamp(int(30 + ring * 60 + center_glow * 120 + (n % 14) - 7))
            g = _clamp(int(8 + ring * 15 + center_glow * 40 + (n % 10) - 5))
            b = _clamp(int(50 + ring * 80 + center_glow * 160 + (n % 18) - 9))
            img.setPixelColor(px, py, QColor(r, g, b))

    return QPixmap.fromImage(img)


_TEXTURE_GENERATORS: dict[str, callable] = {
    "stone": _gen_stone_wall,
    "floor": _gen_stone_floor,
    "ceiling": _gen_ceiling,
    "gate": _gen_gate_barrier,
    "gate_solved": _gen_gate_solved,
    "start": _gen_start_panel,
    "exit": _gen_exit_portal,
}

# ---------------------------------------------------------------------------
# Geometry templates — normalised to [0,1] coordinate space
#
# The view is divided into 3 depth layers. Each layer defines:
#   - left/right x boundaries for the corridor
#   - top/bottom y boundaries for the corridor (ceiling/floor edges)
# These define trapezoids that create the perspective effect.
# ---------------------------------------------------------------------------

# (left_x, right_x, top_y, bottom_y) for each depth layer
_DEPTH_BOUNDS: list[tuple[float, float, float, float]] = [
    (0.00, 1.00, 0.00, 1.00),  # depth 0 — full screen
    (0.15, 0.85, 0.15, 0.85),  # depth 1 — mid corridor
    (0.30, 0.70, 0.30, 0.70),  # depth 2 — far corridor
]

_HALF_PI = math.pi / 2
_TWO_PI = 2.0 * math.pi

# Cardinal direction offsets: (drow, dcol)
_DIR_DELTA: dict[str, tuple[int, int]] = {
    "N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1),
}

_LEFT_OF: dict[str, str] = {"N": "W", "W": "S", "S": "E", "E": "N"}
_RIGHT_OF: dict[str, str] = {"N": "E", "E": "S", "S": "W", "W": "N"}
_OPPOSITE: dict[str, str] = {"N": "S", "S": "N", "E": "W", "W": "E"}

# Key mapping (same as Pygame backend)
_KEY_TO_ACTION: dict[str, str] = {
    "w": "forward", "arrow_up": "forward",
    "s": "backward", "arrow_down": "backward",
    "a": "turn_left", "q": "turn_left", "arrow_left": "turn_left",
    "d": "turn_right", "e": "turn_right", "arrow_right": "turn_right",
}

FACING_ANGLES: dict[str, float] = {
    "N": math.pi / 2, "E": 0.0, "S": -math.pi / 2, "W": math.pi,
}


def _angle_for_facing(f: str) -> float:
    return FACING_ANGLES.get(f, 0.0)


def _facing_for_angle(angle: float) -> str:
    a = angle % _TWO_PI
    if a < math.pi / 4 or a >= 7 * math.pi / 4:
        return "E"
    if a < 3 * math.pi / 4:
        return "N"
    if a < 5 * math.pi / 4:
        return "W"
    return "S"


# ---------------------------------------------------------------------------
# Simple grid helper (from snapshot dict)
# ---------------------------------------------------------------------------

class _Cell:
    __slots__ = ("row", "col", "kind", "visible", "has_gate", "solved",
                 "is_player", "connections")

    def __init__(self, d: dict) -> None:
        self.row: int = d.get("row", 0)
        self.col: int = d.get("col", 0)
        self.kind: str = d.get("kind", "normal")
        self.visible: bool = d.get("visible", False)
        self.has_gate: bool = d.get("has_gate", False)
        self.solved: bool = d.get("solved", False)
        self.is_player: bool = d.get("is_player", False)
        self.connections: set[str] = set(d.get("connections", []))


class _Grid:
    def __init__(self, snapshot: dict) -> None:
        self.width: int = snapshot.get("width", 0)
        self.height: int = snapshot.get("height", 0)
        self._cells: dict[tuple[int, int], _Cell] = {}
        for cd in snapshot.get("cells", []):
            c = _Cell(cd)
            self._cells[(c.row, c.col)] = c

    def cell(self, row: int, col: int) -> _Cell | None:
        return self._cells.get((row, col))

    def has_wall(self, row: int, col: int, direction: str) -> bool:
        """True if there is a wall on the *direction* side of (row, col)."""
        c = self.cell(row, col)
        if c is None or not c.visible:
            return True
        return direction not in c.connections


# ---------------------------------------------------------------------------
# View renderer — draws a single first-person dungeon-crawler perspective
# ---------------------------------------------------------------------------

_VIEW_W = 640
_VIEW_H = 480


def _wall_texture(cell: _Cell | None) -> QPixmap:
    """Select wall texture based on cell type."""
    if cell is not None:
        if cell.has_gate and not cell.solved:
            return _get_texture("gate")
        if cell.has_gate and cell.solved:
            return _get_texture("gate_solved")
        if cell.kind == "start":
            return _get_texture("start")
        if cell.kind == "exit":
            return _get_texture("exit")
    return _get_texture("stone")


def _draw_textured_poly(
    p: QPainter,
    poly: QPolygonF,
    texture: QPixmap,
    fog_depth: int = 0,
    darken: int = 0,
) -> None:
    """Fill *poly* with a tiled *texture*, then apply optional darkening and fog."""
    path = QPainterPath()
    path.addPolygon(poly)
    p.save()
    p.setClipPath(path)
    br = poly.boundingRect()
    p.fillRect(br, QBrush(texture))
    if darken > 0:
        p.fillRect(br, QColor(0, 0, 0, darken))
    if 0 < fog_depth < len(_FOG_ALPHA) and _FOG_ALPHA[fog_depth] > 0:
        fog = QColor(_COL_FOG)
        fog.setAlpha(_FOG_ALPHA[fog_depth])
        p.fillRect(br, fog)
    p.restore()


def _draw_textured_rect(
    p: QPainter,
    rect: QRectF,
    texture: QPixmap,
    fog_depth: int = 0,
    darken: int = 0,
) -> None:
    """Fill *rect* with a tiled *texture*, then apply optional darkening and fog."""
    p.save()
    p.fillRect(rect, QBrush(texture))
    if darken > 0:
        p.fillRect(rect, QColor(0, 0, 0, darken))
    if 0 < fog_depth < len(_FOG_ALPHA) and _FOG_ALPHA[fog_depth] > 0:
        fog = QColor(_COL_FOG)
        fog.setAlpha(_FOG_ALPHA[fog_depth])
        p.fillRect(rect, fog)
    p.restore()


def render_view(grid: _Grid, row: int, col: int, facing: str) -> QPixmap:
    """Render a first-person dungeon-crawler view as a QPixmap."""
    pixmap = QPixmap(_VIEW_W, _VIEW_H)
    pixmap.fill(_COL_FOG)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    w, h = float(_VIEW_W), float(_VIEW_H)
    fwd_dr, fwd_dc = _DIR_DELTA[facing]
    left_dir = _LEFT_OF[facing]
    right_dir = _RIGHT_OF[facing]

    floor_tex = _get_texture("floor")
    ceil_tex = _get_texture("ceiling")

    for depth in reversed(range(3)):
        cr = row + fwd_dr * depth
        cc = col + fwd_dc * depth
        cell = grid.cell(cr, cc)

        lx, rx, ty, by = _DEPTH_BOUNDS[depth]
        if depth < 2:
            nlx, nrx, nty, nby = _DEPTH_BOUNDS[depth + 1]
        else:
            nlx, nrx, nty, nby = 0.40, 0.60, 0.40, 0.60

        # Floor
        floor_poly = QPolygonF([
            QPointF(lx * w, by * h),
            QPointF(rx * w, by * h),
            QPointF(nrx * w, nby * h),
            QPointF(nlx * w, nby * h),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        _draw_textured_poly(p, floor_poly, floor_tex, fog_depth=depth)

        # Ceiling
        ceil_poly = QPolygonF([
            QPointF(lx * w, ty * h),
            QPointF(rx * w, ty * h),
            QPointF(nrx * w, nty * h),
            QPointF(nlx * w, nty * h),
        ])
        _draw_textured_poly(p, ceil_poly, ceil_tex, fog_depth=depth)

        # Wall presence
        has_left_wall = True
        has_right_wall = True
        has_front_wall = True

        if cell is not None and cell.visible:
            has_left_wall = grid.has_wall(cr, cc, left_dir)
            has_right_wall = grid.has_wall(cr, cc, right_dir)
            ahead_r = cr + fwd_dr
            ahead_c = cc + fwd_dc
            ahead_cell = grid.cell(ahead_r, ahead_c)
            if facing in cell.connections:
                has_front_wall = ahead_cell is None or not ahead_cell.visible
            else:
                has_front_wall = True
        else:
            has_front_wall = True

        wall_tex = _wall_texture(cell)

        # Left wall
        if has_left_wall:
            left_poly = QPolygonF([
                QPointF(lx * w, ty * h),
                QPointF(nlx * w, nty * h),
                QPointF(nlx * w, nby * h),
                QPointF(lx * w, by * h),
            ])
            _draw_textured_poly(p, left_poly, wall_tex,
                                fog_depth=depth, darken=50)

        # Right wall
        if has_right_wall:
            right_poly = QPolygonF([
                QPointF(rx * w, ty * h),
                QPointF(nrx * w, nty * h),
                QPointF(nrx * w, nby * h),
                QPointF(rx * w, by * h),
            ])
            _draw_textured_poly(p, right_poly, wall_tex,
                                fog_depth=depth, darken=50)

        # Front wall
        if has_front_wall:
            front_rect = QRectF(nlx * w, nty * h,
                                (nrx - nlx) * w, (nby - nty) * h)
            _draw_textured_rect(p, front_rect, wall_tex,
                                fog_depth=depth if depth > 0 else 0)

        # Side openings
        if not has_left_wall and cell is not None:
            open_rect = QRectF(lx * w, nty * h,
                               (nlx - lx) * w, (nby - nty) * h)
            _draw_textured_rect(p, open_rect, floor_tex,
                                fog_depth=depth, darken=80)

        if not has_right_wall and cell is not None:
            open_rect = QRectF(nrx * w, nty * h,
                               (rx - nrx) * w, (nby - nty) * h)
            _draw_textured_rect(p, open_rect, floor_tex,
                                fog_depth=depth, darken=80)

    current = grid.cell(row, col)
    if current is not None:
        _draw_cell_indicator(p, current, w, h)

    pen = QPen(QColor(30, 30, 50, 120), 1.0)
    p.setPen(pen)
    for depth in range(3):
        lx, rx, ty, by = _DEPTH_BOUNDS[depth]
        p.drawLine(QPointF(lx * w, ty * h), QPointF(lx * w, by * h))
        p.drawLine(QPointF(rx * w, ty * h), QPointF(rx * w, by * h))
        p.drawLine(QPointF(lx * w, ty * h), QPointF(rx * w, ty * h))
        p.drawLine(QPointF(lx * w, by * h), QPointF(rx * w, by * h))

    p.end()
    return pixmap


def _draw_cell_indicator(p: QPainter, cell: _Cell, w: float, h: float) -> None:
    """Draw a text indicator for special cell types near the bottom."""
    text = ""
    color = QColor("#00ff41")
    if cell.has_gate and not cell.solved:
        text = "GATE LOCKED"
        color = _COL_GATE
    elif cell.has_gate and cell.solved:
        text = "GATE OPEN"
        color = _COL_GATE_SOLVED
    elif cell.kind == "start":
        text = "START"
        color = QColor("#4488ff")
    elif cell.kind == "exit":
        text = "EXIT"
        color = _COL_EXIT.lighter(150)

    if not text:
        return

    font = QFont("monospace", 18, QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QPen(color))
    rect = QRectF(0, h * 0.78, w, h * 0.12)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


# ---------------------------------------------------------------------------
# QPaintViewport — simple QWidget that blits the current pixmap
# ---------------------------------------------------------------------------

class QPaintViewport(QWidget):
    """Host widget that displays the backend's current pre-rendered QPixmap.

    When used as a child of a container widget (the viewport host) it tracks
    that container's size via resizeEvent so it always fills the host without
    needing an external layout.
    """

    def __init__(self, backend: QPaintBackend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend = backend
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if parent is not None:
            self.resize(parent.width(), parent.height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        pm = self._backend._current_pixmap
        if pm is None or pm.isNull():
            return
        painter = QPainter(self)
        painter.drawPixmap(
            QRectF(0, 0, self.width(), self.height()).toRect(),
            pm,
        )
        painter.end()


# ---------------------------------------------------------------------------
# QPaintBackend — BaseBackend implementation
# ---------------------------------------------------------------------------

class QPaintBackend(BaseBackend):
    """Pre-rendered dungeon-crawler backend using QPainter."""

    def __init__(self) -> None:
        super().__init__()
        self._viewport: QPaintViewport | None = None
        self._parent_widget: QWidget | None = None
        self._started = False

        self._grid: _Grid | None = None
        self._current_snapshot: dict | None = None
        self._view_cache: dict[tuple[int, int, str], QPixmap] = {}

        self._player_row = 0
        self._player_col = 0
        self._player_angle = _angle_for_facing("S")
        self._facing_str = "S"

        self._current_pixmap: QPixmap | None = None

    # -- BaseBackend lifecycle -----------------------------------------------

    def start(self, parent_widget: QWidget) -> None:
        if self._started:
            return
        self._parent_widget = parent_widget
        self._viewport = QPaintViewport(self, parent_widget)
        # Use the parent's layout if it has one, otherwise fill manually.
        layout = parent_widget.layout()
        if layout is not None:
            layout.addWidget(self._viewport)
        else:
            self._viewport.setGeometry(
                0, 0, parent_widget.width(), parent_widget.height()
            )
        self._viewport.show()
        self._started = True

        if self._current_snapshot is not None:
            self._grid = _Grid(self._current_snapshot)
            self._rebuild_cache()
            self._sync_player_from_snapshot(self._current_snapshot)
            self._update_display()

        log.info("QPaint backend started (%dx%d)", parent_widget.width(), parent_widget.height())

    def stop(self) -> None:
        if self._viewport is not None:
            self._viewport.hide()
            self._viewport = None
        self._started = False
        self._current_pixmap = None
        self._view_cache.clear()
        log.info("QPaint backend stopped")

    def is_ready(self) -> bool:
        return self._started and self._viewport is not None

    # -- Data input ----------------------------------------------------------

    def send_maze_update(self, snapshot_dict: dict) -> None:
        self._current_snapshot = snapshot_dict
        self._grid = _Grid(snapshot_dict)
        self._sync_player_from_snapshot(snapshot_dict)
        self._rebuild_cache()
        self._update_display()

    def send_highlight_player(self, row: int, col: int) -> None:
        self._player_row = row
        self._player_col = col
        self._update_display()

    def send_view_direction(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d in ("N", "S", "E", "W"):
            self._player_angle = _angle_for_facing(d)
            if d != self._facing_str:
                self._facing_str = d
                self._emit_facing(d)
            self._update_display()

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
            new_f = _facing_for_angle(self._player_angle)
            if new_f != self._facing_str:
                self._facing_str = new_f
                self._emit_facing(new_f)
            self._update_display()
        elif action == "turn_right":
            self._player_angle = (self._player_angle - _HALF_PI) % _TWO_PI
            new_f = _facing_for_angle(self._player_angle)
            if new_f != self._facing_str:
                self._facing_str = new_f
                self._emit_facing(new_f)
            self._update_display()
        elif action == "forward":
            self._emit_direction(self._facing_str)
        elif action == "backward":
            self._emit_direction(_OPPOSITE.get(self._facing_str, "S"))

    # -- Cache management ----------------------------------------------------

    def _rebuild_cache(self) -> None:
        """Pre-render all (row, col, facing) views for visible cells."""
        self._view_cache.clear()
        if self._grid is None:
            return
        grid = self._grid
        for (r, c), cell in grid._cells.items():
            if cell.visible:
                for facing in ("N", "S", "E", "W"):
                    key = (r, c, facing)
                    self._view_cache[key] = render_view(grid, r, c, facing)
        log.debug("QPaint cache: %d views pre-rendered", len(self._view_cache))

    def _update_display(self) -> None:
        """Look up the current view and trigger a repaint."""
        key = (self._player_row, self._player_col, self._facing_str)
        pm = self._view_cache.get(key)
        if pm is None and self._grid is not None:
            pm = render_view(self._grid, self._player_row,
                             self._player_col, self._facing_str)
        self._current_pixmap = pm
        if self._viewport is not None:
            self._viewport.update()

    def _sync_player_from_snapshot(self, snapshot_dict: dict) -> None:
        """Extract player position from the snapshot."""
        for cell in snapshot_dict.get("cells", []):
            if cell.get("is_player"):
                self._player_row = int(cell.get("row", 0))
                self._player_col = int(cell.get("col", 0))
                return

    def _handle_resize(self) -> None:
        """Resize the viewport to fill the parent widget (called on host resize)."""
        if self._viewport is None or self._parent_widget is None:
            return
        pw = self._parent_widget
        if self._viewport.layout() is None:
            # Only needed when no layout manages the size (fallback path).
            new_w = max(1, pw.width())
            new_h = max(1, pw.height())
            if self._viewport.width() != new_w or self._viewport.height() != new_h:
                self._viewport.resize(new_w, new_h)

    def viewport_widget(self) -> QWidget | None:
        """Return the viewport widget for layout purposes."""
        return self._viewport
