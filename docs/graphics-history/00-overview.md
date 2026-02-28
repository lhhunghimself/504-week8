# Graphics Renderer Development — Overview & Timeline

This document summarizes the chronology of four graphical renderer backends developed for the Quiz Maze game, from the initial headless CLI through four distinct 3D/2.5D rendering approaches. Each renderer has its own detailed play-by-play document.

**Detailed documents:**
- [01 — Godot Renderer](01-godot-renderer.md)
- [02 — Panda3D Renderer](02-panda3d-renderer.md)
- [03 — Pygame Raycaster](03-pygame-renderer.md)
- [04 — QPainter Pre-Rendered](04-qpaint-renderer.md)

---

## Starting Point: Headless Engine

Before any graphics work, the project had:
- CLI-only game loop (`main.py`)
- Maze generation (`maze.py`) with fog-of-war
- SQLite persistence (`db.py`)
- Puzzle/hint system
- PyQt6 GUI forms (team widgets, puzzle dialogs, scoreboard) on feature branches

The graphics work began with merging three GUI feature branches (`feat/gui-controller`, `feat/gui-forms`, `feat/gui-canvas`) into master, establishing the `MainWindow` + `MazeCanvas` framework.

---

## Timeline

### Phase 1: Godot 4 — External Process with WebSocket Bridge
**Branch:** `feat/gui-canvas`, `debug/godot-draw-harness`

| Step | What Happened |
|------|---------------|
| Merge GUI branches | Merged controller → forms → canvas into master. Fixed PySide6/PyQt6 conflict. 136 tests. |
| Godot not rendering | Window appeared then vanished. Fixed spawn position, process fallback, WebSocket deps. |
| Black screen | Pre-connection message buffer overwrote `maze_update` with `highlight_player`. Changed to FIFO queue. |
| Debug harness | Created `godot_debug_harness.py` for isolated Godot rendering tests. |
| Automated sweep | Added sweep mode: visit every cell × 4 facings, report Godot errors. PASS. |
| Manual testing | Fixed movement signal wiring in harness. Turns worked, moves didn't → signal connection fix. |
| Full game integration | Wired Godot bridge into `MainWindow`. Fixed 2D minimap being suppressed. |
| X11 embedding | Embedded Godot inside PyQt via `--wid`. Black screen → timing race → forced refresh kick sequence at 0/80/220/500ms. |
| Facing indicators | Added facing text, direction arrow on 2D map, Godot minimap overlay via CanvasLayer. |

**Result:** Full 3D renderer with PBR materials, per-cell OmniLight3D, embedded in PyQt via X11. Requires Godot 4 installed externally.

---

### Phase 2: Panda3D — In-Process Embedded Engine
**Branch:** `feat/gui-pygame-renderer` (evolved from `ursula`)

| Step | What Happened |
|------|---------------|
| BaseBackend abstraction | Created `gui/renderers/base_backend.py` — abstract interface for all renderers. Extracted Godot into `GodotBackend`. |
| Feasibility spike | Proved `ShowBase` can be embedded in Qt via `winId()` + `QTimer`-driven `taskMgr.step()`. |
| PandaBackend | Implemented full Panda3D backend: procedural 3D geometry, textures, minimap overlay. |
| GLX errors | Window not mapped yet when Panda3D opened it. Deferred startup until `showEvent`. |
| No walls visible | Dark materials + 30° FOV. Brightened colors, widened to 75°. |
| Keyboard not reaching Panda3D | Added `inject_key()` on BaseBackend, wired through MazeCanvas and MainWindow key events. |
| Viewport sizing | Multiple rounds: Qt layout not finalized at startup → staggered resize timers. HiDPI mismatch → `devicePixelRatioF()`. Exponential back-off polling until sizes converge. |
| Direction mapping | N showed as E. Fixed compass-to-Panda3D heading lookup tables. |
| `--renderer` flag | Added `--renderer {godot,panda3d}` CLI option. Made `--no-godot` fallback deterministic. |

**Result:** In-process 3D renderer with procedural textures. No external dependencies beyond `panda3d` pip package. Eliminated WebSocket overhead and process management.

---

### Phase 3: Pygame — Classic DDA Raycaster
**Branch:** `feat/gui-pygame-renderer`

| Step | What Happened |
|------|---------------|
| Planning | Staged plan: core DDA raycaster → PygameBackend → integration → tests. |
| Implementation | DDA raycaster casting one ray per screen column. `pygame.Surface` blitted to `QLabel` via `QTimer`. Flat colors initially. |
| Code review fixes | Added snapshot-driven player sync, fixed import fallback, proper SDL cleanup. |
| Godot regression | `project.godot` and `texture_gen.gd` missing on this branch. Restored from master. |
| Textures | Added NumPy procedural textures: brick walls, metal floor, ceiling panels, gate/exit/start markers. Vectorized `surfarray.pixels3d` for performance. |
| Mirrored walls | Sign error in `atan2(camera_x * tan_half, 1.0)` → `atan2(-camera_x * tan_half, 1.0)`. |

**Result:** Lightweight Wolfenstein-style raycaster with textured walls, floor, and ceiling. Only needs `pygame` and `numpy` — no GPU, no external engine.

---

### Phase 4: QPainter — Pre-Rendered Dungeon Crawler
**Branch:** `feat/gui-qpaint`

| Step | What Happened |
|------|---------------|
| Concept | Pre-render all possible views (cells × 4 facings ≈ 100 views). Myst-style navigation through static scenes. Pure Qt, no external deps. |
| Implementation | `render_view()` draws depth-layered trapezoids using `QPolygonF` + `QPainter`. `QPaintBackend` manages view cache. 31 tests. |
| Critical bug fixes | Default renderer pointed to absent `panda3d` → crash. Hint regression. Duplicate viewports. Viewport didn't track resize. All four fixed. |
| First textures | QPainter procedural textures (brick, flagstone, panels). 64x64, `QBrush` tiling. |
| Texture quality | Researched Doom PLAYPAL palette. Rewrote all textures: 128px, per-pixel noise, mortar/stain patterns, `QTransform`-scaled brushes, `SmoothPixmapTransform`. |
| QGraphicsScene? | Analyzed and rejected — adds scene graph overhead, doesn't fix texture quality. |
| Qt Quick 3D? | Analyzed and rejected — incomplete PyQt6 bindings, not worth the complexity. |
| Off-center camera | Modified `_DEPTH_BOUNDS` for asymmetric perspective. Vanishing point at ~72% height (eye-level). |
| Per-pixel lighting | NumPy lighting pass on each 640x480 view: point lights, specular, AO, vignette, green tint. ~38ms/view, 3.8s for 100 views. |
| Lazy caching | Changed from "render all upfront" (4s blocking) to on-demand + adjacent pre-rendering via `QTimer.singleShot`. Initial display: 38ms. |

**Result:** Pre-rendered dungeon crawler with Doom-inspired textures, per-pixel lighting, and instant navigation. Zero external dependencies — pure PyQt6 + NumPy.

---

## Comparison Matrix

| Feature | Godot | Panda3D | Pygame | QPainter |
|---------|-------|---------|--------|----------|
| Rendering | True 3D (PBR) | True 3D (procedural) | 2.5D raycaster | Pre-rendered 2D |
| Process | External (WebSocket) | In-process | In-process | In-process |
| GPU Required | Yes (Vulkan/GL) | Yes (OpenGL) | No | No |
| External Deps | Godot 4 binary | `panda3d` pip | `pygame` + `numpy` | `numpy` only |
| Textures | PBR materials | Procedural 3D | Procedural (NumPy) | Procedural (QPainter + NumPy lighting) |
| Lighting | OmniLight3D per cell | Ambient + directional | Distance fog | Per-pixel point lights (simulated) |
| Frame Rate | 60fps (Godot-managed) | ~60fps (QTimer) | ~60fps (QTimer) | Instant (pre-rendered) |
| Initial Load | ~2s (Godot boot) | ~1s (ShowBase init) | ~100ms | ~38ms (current view) |
| Lines of Code | ~400 GDScript + ~300 Python | ~600 Python | ~700 Python | ~900 Python |

---

## Architectural Evolution

```
Phase 1: Godot
  MainWindow → MazeCanvas → WebSocket → Godot Process
  (monolithic, Godot-specific)

Phase 2: Panda3D + BaseBackend Abstraction
  MainWindow → MazeCanvas → BaseBackend ──┬── GodotBackend (extracted)
                                           └── PandaBackend (new)
  (plugin architecture established)

Phase 3: Pygame
  MainWindow → MazeCanvas → BaseBackend ──┬── GodotBackend
                                           ├── PandaBackend
                                           └── PygameBackend (new)
  (lightweight alternative)

Phase 4: QPainter
  MainWindow → MazeCanvas → BaseBackend ──┬── GodotBackend
                                           ├── PandaBackend
                                           ├── PygameBackend
                                           └── QPaintBackend (new)
  (zero-dependency fallback)
```

---

## Recurring Themes

1. **Deferred initialization** — Every renderer hit timing issues where Qt layout wasn't finalized when the renderer tried to read widget sizes. All solved with deferred startup and staggered retry timers.

2. **Coordinate system mismatches** — Godot (Y-up, Z-forward), Panda3D (Z-up, Y-forward), Pygame (screen coords), QPainter (screen coords). Each required compass-to-engine direction mapping.

3. **Keyboard input routing** — Embedded renderers don't receive Qt key events by default. Each needed explicit key injection through `BaseBackend.inject_key()`.

4. **Texture quality iteration** — Every renderer went through flat colors → basic procedural → refined procedural textures. The Doom PLAYPAL research improved QPainter textures dramatically.

5. **Branch file dependencies** — Godot project files on one branch, Python backends on another. Missing files caused silent failures (gray screens, import errors) discovered only during cross-renderer testing.

6. **Debug harnesses are essential** — Both Godot and Panda3D required standalone harnesses to isolate rendering from game logic during debugging.

---

## Final Test Results

After all merges to master:
- **247 tests passing**
- **4 renderers** available via `--renderer {godot,panda3d,pygame,qpaint}`
- **Default:** `qpaint` (zero external dependencies)
