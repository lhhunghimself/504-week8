# QPainter Pre-Rendered Renderer — Development History

**Branch:** `feat/gui-qpaint`
**Key commits:** `f2aa92c`
**Date:** 2026-02-27 through 2026-02-28

---

## Context

The QPainter backend takes a radically different approach: instead of real-time rendering, it pre-computes every possible first-person view as a static `QPixmap`. Since the player can only see 3 cells deep, the viewable area is a small region around the player. With ~25 visible cells × 4 facings ≈ ~100 views per maze, pre-rendering is fast and navigation is instant. The aesthetic is Myst-style: click through pre-rendered scenes. No external engines, no SDL — pure Qt.

---

## Play-by-Play

### 1. Concept and Planning

**Prompt:** "Commit this [Pygame textures] and let's branch off one more feature branch qpaint where we will use QPainter to render pre-calculated maze views."

**Response:** Committed the Pygame texture work. Created `feat/gui-qpaint` from master.

**Prompt:** "The idea will be to precalculate all possible views with range 3 and above which is not many. Anything more than 3 apart simply will not be rendered, so it is basically a 3x3 area that needs to be considered. This should make this very fast since all views are pre-calculated."

**Response:** Designed the architecture: `_Grid` and `_Cell` lightweight data structures parse the `MazeSnapshot`, `render_view()` draws a first-person dungeon-crawler perspective using depth layers (0–2) with QPainter trapezoids for walls/floor/ceiling, `QPaintViewport` displays the current `QPixmap`, and `QPaintBackend` manages the cache. Created a detailed plan.

---

### 2. Implementation

**Prompt:** "Implement the plan. Don't stop until you have completed all the to-dos."

**Response:** Implemented the full QPaint backend:
- **`_Cell` / `_Grid`** — Lightweight maze representation parsed from snapshot dicts
- **`_DEPTH_BOUNDS`** — Perspective bounds for 3 depth layers (near, mid, far)
- **`render_view()`** — Draws floor/ceiling trapezoids, left/right wall trapezoids, front wall rectangles, side openings, and cell indicators. Uses `QPolygonF`, `QPainterPath`, and depth fog
- **`QPaintViewport`** — `QWidget` displaying the current `QPixmap` with auto-scaling on resize
- **`QPaintBackend`** — `BaseBackend` subclass managing the view cache, player tracking, and key injection (WASD + Q/E)
- **Test suite** — 31 tests covering `_Grid`, `render_view`, cache lifecycle, key injection, and viewport

---

### 3. Code Review

**Prompt:** "Review the code."

**Response:** Found four issues ordered by severity:
1. **Critical — Default GUI path broken:** `main.py` defaulted renderer to `panda3d`, but `panda3d_backend.py` didn't exist on this branch. Import failed immediately.
2. **High — Hint regression:** Blank hint argument broke the `test_hint_blank_arg_returns_options` integration test.
3. **Medium — Duplicate viewports:** Both `gui_main.py` and `QPaintBackend.start()` created `QPaintViewport` instances, resulting in 2 viewports.
4. **Medium — Viewport doesn't track resize:** `QPaintViewport` used fixed geometry, not responding to parent resize.

**Prompt:** "Can you fix the identified issues."

**Response:** Fixed all four:
1. Changed default renderer to `qpaint` in `main.py`, `gui_main.py`, and `--no-godot` fallback
2. Fixed `GameEngine.handle()` to treat blank/whitespace hint args as "show options"
3. Made `QPaintBackend.start()` solely responsible for creating the viewport
4. Implemented `resizeEvent` on `QPaintViewport` and `_handle_resize()` fallback

---

### 4. Adding Textures — First Pass

**Prompt:** "This works but can we have textures from something like Unreal or Quake? Should be easy since they are all pre-rendered."

**Response:** Added procedural textures using QPainter drawing operations (no NumPy — pure Qt):
- `_gen_stone_wall()` — Brick pattern with dark mortar
- `_gen_stone_floor()` — Flagstone pattern
- `_gen_ceiling()` — Dark panel texture
- `_gen_gate_barrier()` — Warning stripe pattern
- `_gen_gate_solved()` — Green/open gate
- `_gen_start_panel()` — Blue start marker
- `_gen_exit_portal()` — Purple exit glow

Used `QBrush(QPixmap)` to tile textures into wall polygons with `QPainterPath` clipping. 64x64 texture size.

---

### 5. Texture Quality Improvement

**Prompt:** "These textures aren't very good. Can you look through screenshots or Githubs of Doom or Duke Nukem clones and crawlers to find something more appropriate."

**Response:** Researched classic FPS texture design — Doom's PLAYPAL color palette, Slynyrd's pixel art brick tutorials, dungeon crawler aesthetics from Eye of the Beholder. Key findings:
- Doom textures use a specific 256-color palette with warm browns and cool grays
- Brick patterns need mortar lines, staining, and edge highlight variation
- Aging effects (discoloration, damage) create visual depth

Rewrote all procedural texture generators:
- Increased texture size from 64 to 128 pixels (4x the detail)
- Used Doom PLAYPAL-inspired color palettes (warm browns, cool stone grays)
- Added per-pixel deterministic noise via `_pnoise()` hash function
- Brick/flagstone patterns with distinct mortar, random stains, edge highlights
- Enabled `QPainter.RenderHint.SmoothPixmapTransform` (bilinear filtering)
- Created `_scaled_brush()` using `QTransform` to stretch textures to polygon bounding boxes (eliminating fixed-size tiling artifacts)

---

### 6. Merging All Feature Branches

**Prompt:** "Commit and push."

**Response:** Committed QPaint textures. Pushed to origin.

**Prompt:** "Now merge the feature branches into the master starting from godot, panda3d, pygame, qpaint."

**Response:** Merged in order:
1. `debug/godot-draw-harness` → master (Godot stabilization + facing indicators)
2. `feat/gui-pygame-renderer` → master (Panda3D + Pygame + BaseBackend). Resolved conflicts in `gui_main.py`, `main.py`, `maze_canvas.py`, `requirements.txt`
3. `feat/gui-qpaint` → master (QPaint backend). Resolved conflicts in `gui_main.py` and `main.py`

All 247 tests pass after merges.

---

### 7. Texture Quality — QGraphicsScene vs Qt Quick 3D

**Prompt:** "Would QGraphicsScene work better for a more uniform unpixelated texture?"

**Response:** No. QGraphicsScene is a 2D scene graph for managing interactive items — adds overhead without addressing the core texture issues. The real fixes (already applied): increase texture size to 128, enable `SmoothPixmapTransform`, use `QTransform`-scaled brushes.

**Prompt:** "How about Qt Quick 3D?"

**Response:** Qt Quick 3D has actual 3D rendering with PBR materials, but PyQt6 bindings for it are incomplete/missing. Qt 3D (the older framework) has better Python support but is still complex to set up. Neither would be worth the effort given the pre-rendered approach works well.

---

### 8. Off-Center Perspective

**Prompt:** "The rendering is still not great — the off-center camera of Godot is very nice — can we do the same with QPainter?"

**Response:** Diagnosed the difference: Godot's `Camera3D` sits at eye level (~80% wall height), creating an asymmetric perspective where you see more floor than ceiling. QPaint had symmetric perspective with the vanishing point dead center.

**Fix:** Modified `_DEPTH_BOUNDS` to create asymmetric trapezoids:
```python
_DEPTH_BOUNDS = [
    (0.00, 1.00, 0.00, 1.00),   # depth 0 — full screen
    (0.15, 0.85, 0.22, 0.90),   # depth 1 — ceiling recedes faster
    (0.30, 0.70, 0.45, 0.81),   # depth 2 — far end sits low
]
```
The vanishing point now sits at ~72% from the top of the screen, matching Godot's eye-level feel.

---

### 9. Per-Pixel Lighting Pass

**Prompt:** "That's not bad but the raytraced textures in Godot are not there."

**Prompt:** "You only have to render the 100 or so scenes — this should be doable with the QPaint method."

**Response:** Since only ~100 views are pre-rendered, added a full per-pixel lighting pass using NumPy on each 640x480 `QPixmap`:
- **Point light at vanishing point** — Simulates wall sconce in the next cell (green-tinted, radial falloff)
- **Torch light from player** — Warm light below eye level (simulates carried light source)
- **Specular highlight** — Concentrated bright spot at the vanishing point (simulates PBR roughness=0.9)
- **Ambient occlusion** — Extra darkening at floor/ceiling edges where walls meet surfaces
- **Vignette** — Edge darkening for atmosphere
- **Green tint** — RGB multipliers (R×0.92, G×1.12, B×0.82) match Godot's green OmniLight3D
- Reduced fog alpha from `[0, 60, 130]` to `[0, 25, 60]` since lighting handles depth darkening
- Reduced side-wall darken from 50 to 30

Performance: ~38ms per view. 100 views rendered in ~3.8 seconds total at maze load.

---

### 10. Lazy Caching with Adjacent Pre-Rendering

**Prompt:** "It is a bit slow — is it possible to cache all the possible next views to make it a bit faster? At any point there are only a few possible next scenes."

**Response:** Changed from "render all views upfront" (blocking ~4 seconds) to lazy rendering with adjacent pre-caching:
- **Current view:** Rendered on-demand when needed (~38ms, one view)
- **Adjacent views:** After displaying, `_schedule_prerender()` queues views reachable by one action (3 turns + forward cell × 4 facings + backward cell × 4 facings ≈ 11 views)
- **Background rendering:** `QTimer.singleShot(0, ...)` renders one queued view per event-loop iteration, keeping UI responsive
- **Cache hits:** Subsequent navigation almost always hits a pre-rendered view

Initial display improved from ~4 seconds to ~38ms.

---

## Key Files

| File | Purpose |
|------|---------|
| `gui/renderers/qpaint_backend.py` | Everything: textures, renderer, viewport, backend, lighting |
| `tests/test_qpaint_backend.py` | 31-test suite for grid, rendering, cache, viewport |

## Rendering Architecture

```
QPaintBackend
  ├── _Grid (parsed from MazeSnapshot)
  ├── render_view() → QPixmap (640x480)
  │     ├── QPainter draws textured trapezoids (3 depth layers)
  │     │     ├── Floor polygons (flagstone texture)
  │     │     ├── Ceiling polygons (dark panel texture)
  │     │     ├── Left/Right wall trapezoids (stone/gate texture)
  │     │     ├── Front wall rectangles
  │     │     └── Side openings (dark floor texture)
  │     ├── Depth fog overlay (reduced alpha)
  │     └── _apply_lighting() — NumPy per-pixel pass
  │           ├── Point light at vanishing point
  │           ├── Torch light from player position
  │           ├── Specular highlight
  │           ├── Ambient occlusion (floor/ceiling edges)
  │           ├── Vignette
  │           └── Green tint (R×0.92, G×1.12, B×0.82)
  ├── _view_cache: dict[(row, col, facing)] → QPixmap
  │     ├── Current view: rendered on-demand
  │     └── Adjacent views: pre-rendered via QTimer.singleShot
  └── QPaintViewport (QWidget displaying current QPixmap)
```

## Lessons Learned

1. **Pre-rendering makes expensive effects free** — Per-pixel lighting, specular, AO — all affordable when you only render ~100 views once.
2. **Asymmetric perspective sells realism** — Moving the vanishing point from 50% to 72% height dramatically improved the feel.
3. **Lazy caching with adjacent pre-render** — Best of both worlds: instant first display, instant navigation, no upfront blocking.
4. **Texture scaling > tiling** — `QTransform`-scaled brushes that stretch to polygon bounds look far better than fixed-size tiling.
5. **Classic game research pays off** — Doom PLAYPAL colors and brick pattern conventions produced much better textures than naive procedural generation.
