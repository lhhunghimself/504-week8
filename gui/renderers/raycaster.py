"""Pure Pygame raycaster -- Wolfenstein-style first-person renderer.

No Qt dependency.  Accepts a ``pygame.Surface`` and draws a complete frame
with DDA wall-casting, procedurally-textured walls/floors/ceilings, distance
fog, and a minimap overlay.

Used by ``PygameBackend`` and the standalone validation script.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pygame
import pygame.surfarray

# ---------------------------------------------------------------------------
# Colour palette — minimap and fog
# ---------------------------------------------------------------------------

COLOR_FOG: tuple[int, int, int] = (26, 26, 46)

COLOR_CEILING: tuple[int, int, int] = (140, 102, 179)
COLOR_FLOOR: tuple[int, int, int] = (23, 33, 61)
COLOR_WALL_NS: tuple[int, int, int] = (185, 180, 210)
COLOR_WALL_EW: tuple[int, int, int] = (155, 150, 185)
COLOR_GATE_WALL: tuple[int, int, int] = (245, 166, 35)
COLOR_GATE_SOLVED_WALL: tuple[int, int, int] = (83, 191, 106)
COLOR_START_WALL: tuple[int, int, int] = (15, 52, 96)
COLOR_EXIT_WALL: tuple[int, int, int] = (82, 51, 131)

COLOR_MM_FOG: tuple[int, int, int] = (26, 26, 46)
COLOR_MM_VISIBLE: tuple[int, int, int] = (22, 33, 62)
COLOR_MM_START: tuple[int, int, int] = (15, 52, 96)
COLOR_MM_EXIT: tuple[int, int, int] = (82, 51, 131)
COLOR_MM_PLAYER: tuple[int, int, int] = (233, 69, 96)
COLOR_MM_GATE: tuple[int, int, int] = (245, 166, 35)
COLOR_MM_GATE_SOLVED: tuple[int, int, int] = (83, 191, 106)
COLOR_MM_CONN: tuple[int, int, int] = (0, 255, 65)
COLOR_MM_ARROW: tuple[int, int, int] = (255, 255, 255)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FOV: float = math.pi / 3  # 60 degrees
MAX_DEPTH: float = 32.0
TEX_SIZE: int = 64
_TWO_PI: float = 2.0 * math.pi
_FOG_VEC = np.array(COLOR_FOG, dtype=np.float32)
_DARK_FACTOR: float = 0.8

# Angle convention: 0 = East (+x), counter-clockwise positive.
# In world coordinates x = column (right), y = row (down).
# ray_dir = (cos(a), -sin(a)) so positive angle goes *up* (North).
FACING_ANGLES: dict[str, float] = {
    "N": math.pi / 2,
    "E": 0.0,
    "S": -math.pi / 2,
    "W": math.pi,
}


def angle_for_facing(facing: str) -> float:
    """Cardinal direction string to angle in radians."""
    return FACING_ANGLES.get(facing, 0.0)


def facing_for_angle(angle: float) -> str:
    """Snap an arbitrary angle to the nearest cardinal direction."""
    a = angle % _TWO_PI
    if a < math.pi / 4 or a >= 7 * math.pi / 4:
        return "E"
    if a < 3 * math.pi / 4:
        return "N"
    if a < 5 * math.pi / 4:
        return "W"
    return "S"


# ---------------------------------------------------------------------------
# Grid data structure
# ---------------------------------------------------------------------------

@dataclass
class CellData:
    walls: dict  # {"N": bool, "S": bool, "E": bool, "W": bool}
    kind: str = "normal"
    visible: bool = False
    has_gate: bool = False
    solved: bool = False
    is_player: bool = False


@dataclass
class Grid:
    width: int
    height: int
    cells: list = field(default_factory=list)  # 2-D  [row][col]

    def cell(self, row: int, col: int) -> CellData | None:
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.cells[row][col]
        return None


def build_grid(snapshot_dict: dict) -> Grid:
    """Convert a snapshot dict (from ``GameEngine``) into a raycaster ``Grid``."""
    w = snapshot_dict.get("width", 0)
    h = snapshot_dict.get("height", 0)
    raw = snapshot_dict.get("cells", [])

    cells = [
        [CellData(walls={"N": True, "S": True, "E": True, "W": True})
         for _ in range(w)]
        for _ in range(h)
    ]
    for c in raw:
        r, col = c["row"], c["col"]
        if 0 <= r < h and 0 <= col < w:
            conns = set(c.get("connections", []))
            cells[r][col] = CellData(
                walls={
                    "N": "N" not in conns,
                    "S": "S" not in conns,
                    "E": "E" not in conns,
                    "W": "W" not in conns,
                },
                kind=c.get("kind", "normal"),
                visible=c.get("visible", False),
                has_gate=c.get("has_gate", False),
                solved=c.get("solved", False),
                is_player=c.get("is_player", False),
            )
    return Grid(width=w, height=h, cells=cells)


# ---------------------------------------------------------------------------
# Procedural texture generation (ported from Godot texture_gen.gd)
# ---------------------------------------------------------------------------

_texture_cache: dict[str, np.ndarray] | None = None


def _gen_brick_wall() -> np.ndarray:
    """Green-tinted brick pattern with mortar lines."""
    tex = np.zeros((TEX_SIZE, TEX_SIZE, 3), dtype=np.uint8)
    mortar = np.array([20, 31, 20], dtype=np.uint8)
    brick_a = np.array([31, 46, 31], dtype=np.int16)
    brick_b = np.array([26, 38, 26], dtype=np.int16)
    tex[:] = mortar

    rng = np.random.RandomState(42)
    brick_h, brick_w, mortar_px = 8, 16, 1

    for row_idx in range(TEX_SIZE // brick_h):
        y0 = row_idx * brick_h + mortar_px
        offset = (brick_w // 2) if (row_idx % 2 == 1) else 0
        for col_idx in range((TEX_SIZE // brick_w) + 1):
            x0 = col_idx * brick_w + offset + mortar_px
            base = brick_a if (row_idx + col_idx) % 2 == 0 else brick_b
            ye = min(y0 + brick_h - mortar_px, TEX_SIZE)
            xe = min(x0 + brick_w - mortar_px, TEX_SIZE)
            if x0 >= TEX_SIZE or y0 >= TEX_SIZE or ye <= y0 or xe <= x0:
                continue
            noise = rng.randint(-5, 6, size=(ye - y0, xe - x0, 3)).astype(np.int16)
            tex[y0:ye, x0:xe] = np.clip(base + noise, 0, 255).astype(np.uint8)
    return tex


def _gen_metal_floor() -> np.ndarray:
    """Dark metal with grid lines."""
    rng = np.random.RandomState(43)
    base = np.array([15.3, 20.4, 30.6], dtype=np.float32)
    noise = rng.uniform(-7.5, 7.5, (TEX_SIZE, TEX_SIZE, 1)).astype(np.float32)
    ys, xs = np.arange(TEX_SIZE), np.arange(TEX_SIZE)
    grid = np.maximum(
        (ys % 16 == 0).astype(np.float32)[:, None],
        (xs % 16 == 0).astype(np.float32)[None, :],
    )[:, :, None]
    boost = grid * np.array([12.75, 15.3, 10.2], dtype=np.float32)
    return np.clip(base + noise + boost, 0, 255).astype(np.uint8)


def _gen_ceiling_panel() -> np.ndarray:
    """Dark panel with subtle panel edges."""
    rng = np.random.RandomState(44)
    base = np.array([7.65, 10.2, 15.3], dtype=np.float32)
    noise = rng.uniform(-2.5, 2.5, (TEX_SIZE, TEX_SIZE, 1)).astype(np.float32)
    ys, xs = np.arange(TEX_SIZE), np.arange(TEX_SIZE)
    edge = np.maximum(
        (ys % 32 == 0).astype(np.float32)[:, None],
        (xs % 32 == 0).astype(np.float32)[None, :],
    )[:, :, None]
    boost = edge * np.array([7.65, 10.2, 7.65], dtype=np.float32)
    return np.clip(base + noise + boost, 0, 255).astype(np.uint8)


def _gen_gate_texture() -> np.ndarray:
    """Glowing orange energy barrier."""
    base = np.array([178.5, 114.75, 25.5], dtype=np.float32)
    xs = np.arange(TEX_SIZE, dtype=np.float32)
    ys = np.arange(TEX_SIZE, dtype=np.float32)
    dist_center = np.abs(xs - 32.0) / 32.0
    wave = np.sin(ys * 0.3) * 0.1
    glow = 1.0 - dist_center[None, :] + wave[:, None]
    tex = np.zeros((TEX_SIZE, TEX_SIZE, 3), dtype=np.float32)
    tex[:, :, 0] = base[0] * glow
    tex[:, :, 1] = base[1] * glow
    tex[:, :, 2] = base[2] * glow * 0.5
    return np.clip(tex, 0, 255).astype(np.uint8)


def _gen_gate_solved_texture() -> np.ndarray:
    """Green variant of the energy barrier for solved gates."""
    base = np.array([53.0, 163.0, 68.0], dtype=np.float32)
    xs = np.arange(TEX_SIZE, dtype=np.float32)
    ys = np.arange(TEX_SIZE, dtype=np.float32)
    dist_center = np.abs(xs - 32.0) / 32.0
    wave = np.sin(ys * 0.3) * 0.1
    glow = 1.0 - dist_center[None, :] + wave[:, None]
    tex = np.zeros((TEX_SIZE, TEX_SIZE, 3), dtype=np.float32)
    tex[:, :, 0] = base[0] * glow
    tex[:, :, 1] = base[1] * glow
    tex[:, :, 2] = base[2] * glow * 0.5
    return np.clip(tex, 0, 255).astype(np.uint8)


def _gen_start_texture() -> np.ndarray:
    """Blue-tinted wall for start cell."""
    rng = np.random.RandomState(46)
    base = np.array([12.75, 40.8, 76.5], dtype=np.float32)
    noise = rng.uniform(-5, 5, (TEX_SIZE, TEX_SIZE, 1)).astype(np.float32)
    ys, xs = np.arange(TEX_SIZE), np.arange(TEX_SIZE)
    grid = np.maximum(
        (ys % 16 == 0).astype(np.float32)[:, None],
        (xs % 16 == 0).astype(np.float32)[None, :],
    )[:, :, None]
    boost = grid * np.array([5.0, 10.0, 15.0], dtype=np.float32)
    return np.clip(base + noise + boost, 0, 255).astype(np.uint8)


def _gen_exit_portal() -> np.ndarray:
    """Purple concentric rings."""
    ys, xs = np.mgrid[0:TEX_SIZE, 0:TEX_SIZE].astype(np.float32)
    dist = np.sqrt((xs - 32.0) ** 2 + (ys - 32.0) ** 2) / 32.0
    ring = np.sin(dist * 10.0) * 0.5 + 0.5
    tex = np.zeros((TEX_SIZE, TEX_SIZE, 3), dtype=np.float32)
    tex[:, :, 0] = 102.0 * ring * np.maximum(1.0 - dist, 0.0)
    tex[:, :, 1] = 25.5 * ring
    tex[:, :, 2] = 153.0 * ring * np.maximum(1.0 - dist * 0.5, 0.0)
    return np.clip(tex, 0, 255).astype(np.uint8)


def _darken(tex: np.ndarray) -> np.ndarray:
    """Return a slightly darker copy of *tex* for E/W-wall side shading."""
    return (tex.astype(np.float32) * _DARK_FACTOR).astype(np.uint8)


def _get_textures() -> dict[str, np.ndarray]:
    """Lazily generate and cache all procedural textures."""
    global _texture_cache
    if _texture_cache is not None:
        return _texture_cache

    wall = _gen_brick_wall()
    gate = _gen_gate_texture()
    gate_solved = _gen_gate_solved_texture()
    start = _gen_start_texture()
    exit_ = _gen_exit_portal()

    _texture_cache = {
        "wall": wall,
        "wall_dark": _darken(wall),
        "gate": gate,
        "gate_dark": _darken(gate),
        "gate_solved": gate_solved,
        "gate_solved_dark": _darken(gate_solved),
        "start": start,
        "start_dark": _darken(start),
        "exit": exit_,
        "exit_dark": _darken(exit_),
        "floor": _gen_metal_floor(),
        "ceiling": _gen_ceiling_panel(),
    }
    return _texture_cache


# ---------------------------------------------------------------------------
# DDA raycasting
# ---------------------------------------------------------------------------

@dataclass
class RayHit:
    distance: float
    side: int        # 0 = vertical grid-line (E/W wall), 1 = horizontal (N/S wall)
    cell_row: int
    cell_col: int
    wall_dir: str    # "N" / "S" / "E" / "W"
    wall_x: float = 0.0  # 0-1 fractional hit position along the wall face


def cast_ray(grid: Grid, px: float, py: float, angle: float) -> RayHit | None:
    """Cast a single ray from *(px, py)* at *angle* through *grid*.

    Returns the first wall hit, or ``None`` if the ray escapes (should not
    happen in a properly bounded maze).
    """
    if grid.width == 0 or grid.height == 0:
        return None

    ray_dx = math.cos(angle)
    ray_dy = -math.sin(angle)

    map_x = max(0, min(int(px), grid.width - 1))
    map_y = max(0, min(int(py), grid.height - 1))

    abs_dx = max(abs(ray_dx), 1e-10)
    abs_dy = max(abs(ray_dy), 1e-10)
    delta_x = 1.0 / abs_dx
    delta_y = 1.0 / abs_dy

    if ray_dx < 0:
        step_x, side_x = -1, (px - map_x) * delta_x
    else:
        step_x, side_x = 1, (map_x + 1.0 - px) * delta_x

    if ray_dy < 0:
        step_y, side_y = -1, (py - map_y) * delta_y
    else:
        step_y, side_y = 1, (map_y + 1.0 - py) * delta_y

    limit = 2 * (grid.width + grid.height) + 8
    for _ in range(limit):
        if side_x < side_y:
            wall_d = "E" if step_x > 0 else "W"
            cell = grid.cell(map_y, map_x)
            if cell is None or cell.walls.get(wall_d, True):
                wx = (py + side_x * ray_dy) % 1.0
                return RayHit(side_x, 0, map_y, map_x, wall_d, wx)
            nxt = map_x + step_x
            if nxt < 0 or nxt >= grid.width:
                wx = (py + side_x * ray_dy) % 1.0
                return RayHit(side_x, 0, map_y, map_x, wall_d, wx)
            side_x += delta_x
            map_x = nxt
        else:
            wall_d = "S" if step_y > 0 else "N"
            cell = grid.cell(map_y, map_x)
            if cell is None or cell.walls.get(wall_d, True):
                wx = (px + side_y * ray_dx) % 1.0
                return RayHit(side_y, 1, map_y, map_x, wall_d, wx)
            nxt = map_y + step_y
            if nxt < 0 or nxt >= grid.height:
                wx = (px + side_y * ray_dx) % 1.0
                return RayHit(side_y, 1, map_y, map_x, wall_d, wx)
            side_y += delta_y
            map_y = nxt

    return None


# ---------------------------------------------------------------------------
# Texture selection
# ---------------------------------------------------------------------------

def _wall_texture(
    hit: RayHit,
    cell: CellData | None,
    textures: dict[str, np.ndarray],
) -> np.ndarray:
    """Pick the right texture for a wall hit (with side-dependent darkening)."""
    dark = "_dark" if hit.side == 0 else ""
    if cell is not None:
        if cell.has_gate and not cell.solved:
            return textures[f"gate{dark}"]
        if cell.has_gate and cell.solved:
            return textures[f"gate_solved{dark}"]
        if cell.kind == "start":
            return textures[f"start{dark}"]
        if cell.kind == "exit":
            return textures[f"exit{dark}"]
    return textures[f"wall{dark}"]


# ---------------------------------------------------------------------------
# Frame rendering
# ---------------------------------------------------------------------------

def render_frame(
    surface: pygame.Surface,
    grid: Grid,
    player_x: float,
    player_y: float,
    player_angle: float,
    width: int,
    height: int,
) -> None:
    """Draw one complete first-person raycaster frame onto *surface*."""
    if width <= 0 or height <= 0:
        return

    textures = _get_textures()
    floor_tex = textures["floor"]
    ceil_tex = textures["ceiling"]

    frame = np.zeros((width, height, 3), dtype=np.uint8)

    half_h = height / 2.0
    half_h_int = int(half_h)
    tan_half = math.tan(FOV / 2.0)

    # --- Floor / ceiling (row-by-row, vectorized across columns) -----------
    fwd_x = math.cos(player_angle)
    fwd_y = -math.sin(player_angle)
    right_x = math.sin(player_angle)
    right_y = math.cos(player_angle)

    camera_xs = 2.0 * np.arange(width, dtype=np.float32) / max(width, 1) - 1.0
    right_offsets = camera_xs * tan_half

    col_dx = fwd_x + right_offsets * right_x
    col_dy = fwd_y + right_offsets * right_y

    for y in range(half_h_int + 1, height):
        p = y - half_h
        if p <= 0:
            continue
        row_dist = half_h / p

        fx = player_x + row_dist * col_dx
        fy = player_y + row_dist * col_dy

        tx = (fx * TEX_SIZE).astype(np.int32) % TEX_SIZE
        ty = (fy * TEX_SIZE).astype(np.int32) % TEX_SIZE

        t = min(1.0, row_dist / MAX_DEPTH)
        t = t * t
        inv_t = np.float32(1.0 - t)
        fog_contrib = _FOG_VEC * np.float32(t)

        fc = floor_tex[ty, tx].astype(np.float32) * inv_t + fog_contrib
        frame[:, y, :] = fc.astype(np.uint8)

        cy = height - 1 - y
        if 0 <= cy < height:
            cc = ceil_tex[ty, tx].astype(np.float32) * inv_t + fog_contrib
            frame[:, cy, :] = cc.astype(np.uint8)

    if half_h_int < height:
        frame[:, half_h_int, :] = COLOR_FOG

    # --- Walls (column-by-column, vectorized within each strip) ------------
    for col in range(width):
        camera_x = camera_xs[col]
        ray_angle = player_angle + math.atan2(-camera_x * tan_half, 1.0)

        hit = cast_ray(grid, player_x, player_y, ray_angle)
        if hit is None:
            continue

        perp = hit.distance * math.cos(ray_angle - player_angle)
        if perp < 0.01:
            perp = 0.01

        strip_h = height / perp
        y0 = max(0, int(half_h - strip_h / 2))
        y1 = min(height, int(half_h + strip_h / 2))
        if y1 <= y0:
            continue

        cell = grid.cell(hit.cell_row, hit.cell_col)
        tex = _wall_texture(hit, cell, textures)
        tex_u = int(hit.wall_x * TEX_SIZE) % TEX_SIZE

        ys = np.arange(y0, y1, dtype=np.float32)
        tex_vs = ((ys - (half_h - strip_h / 2)) / strip_h * TEX_SIZE).astype(np.int32)
        tex_vs = np.clip(tex_vs, 0, TEX_SIZE - 1)

        colors = tex[tex_vs, tex_u].astype(np.float32)

        t = min(1.0, perp / MAX_DEPTH)
        t = t * t
        colors = colors * np.float32(1.0 - t) + _FOG_VEC * np.float32(t)

        frame[col, y0:y1, :] = colors.astype(np.uint8)

    # Push the numpy frame to the pygame surface
    pygame.surfarray.blit_array(surface, frame)

    # Minimap overlay (drawn on top using pygame primitives)
    _draw_minimap(surface, grid, player_x, player_y, player_angle, width, height)


# ---------------------------------------------------------------------------
# Minimap overlay
# ---------------------------------------------------------------------------

def _mm_cell_color(cell: CellData) -> tuple[int, int, int]:
    if not cell.visible:
        return COLOR_MM_FOG
    if cell.is_player:
        return COLOR_MM_PLAYER
    if cell.has_gate and not cell.solved:
        return COLOR_MM_GATE
    if cell.has_gate and cell.solved:
        return COLOR_MM_GATE_SOLVED
    if cell.kind == "start":
        return COLOR_MM_START
    if cell.kind == "exit":
        return COLOR_MM_EXIT
    return COLOR_MM_VISIBLE


def _draw_minimap(
    surface: pygame.Surface,
    grid: Grid,
    px: float,
    py: float,
    angle: float,
    scr_w: int,
    scr_h: int,
) -> None:
    if grid.width == 0 or grid.height == 0:
        return

    cell_px = max(4, min(12, min(scr_w // 6, scr_h // 6) // max(grid.width, grid.height)))
    gap = max(1, cell_px // 8)
    stride = cell_px + gap
    total_w = grid.width * stride - gap
    total_h = grid.height * stride - gap
    margin = 8
    ox = scr_w - total_w - margin
    oy = margin

    bg_pad = 4
    bg = pygame.Surface((total_w + bg_pad * 2, total_h + bg_pad * 2), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 153))
    surface.blit(bg, (ox - bg_pad, oy - bg_pad))

    for row in range(grid.height):
        for col in range(grid.width):
            cell = grid.cell(row, col)
            if cell is None:
                continue
            x = ox + col * stride
            y = oy + row * stride
            surface.fill(_mm_cell_color(cell), (x, y, cell_px, cell_px))
            if cell.visible:
                if not cell.walls.get("E", True):
                    surface.fill(COLOR_MM_CONN, (x + cell_px, y + cell_px // 2 - 1, gap, 2))
                if not cell.walls.get("S", True):
                    surface.fill(COLOR_MM_CONN, (x + cell_px // 2 - 1, y + cell_px, 2, gap))

    # Player arrow
    mm_px = ox + px * stride - gap / 2.0
    mm_py = oy + py * stride - gap / 2.0

    arrow_len = cell_px * 0.6
    tip_x = mm_px + arrow_len * math.cos(angle)
    tip_y = mm_py - arrow_len * math.sin(angle)

    wing_a = math.pi * 0.75
    wing_len = arrow_len * 0.5
    w1x = mm_px + wing_len * math.cos(angle + wing_a)
    w1y = mm_py - wing_len * math.sin(angle + wing_a)
    w2x = mm_px + wing_len * math.cos(angle - wing_a)
    w2y = mm_py - wing_len * math.sin(angle - wing_a)

    pygame.draw.polygon(
        surface, COLOR_MM_ARROW,
        [(int(tip_x), int(tip_y)), (int(w1x), int(w1y)), (int(w2x), int(w2y))],
    )
