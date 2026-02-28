# Pygame Raycaster Renderer — Development History

**Branch:** `feat/gui-pygame-renderer`
**Key commits:** `ef3b6c2` (textures + Godot file restore)
**Date:** 2026-02-27

---

## Context

After Panda3D was working, the goal was a lightweight Pygame-based raycaster — a classic DDA (Digital Differential Analyzer) algorithm renderer like Wolfenstein 3D. Pygame runs in-process with a `pygame.Surface` embedded in Qt via raw pixel blitting. No GPU required.

---

## Play-by-Play

### 1. Planning

**Prompt:** "Commit and push then branch off a new feature branch from master for Pygame. We will try to implement this in Pygame too."

**Response:** Committed the Panda3D fixes and pushed. Created `feat/gui-pygame-renderer` from master.

**Prompt:** "Plan out an equivalent implementation using Pygame. Do it in a staged manner making sure that the engine draws all the views properly first and then integrate with the rest of the game."

**Response:** Drafted a staged plan: (1) core raycaster module with DDA algorithm, (2) `PygameBackend` implementing `BaseBackend`, (3) integration with `gui_main.py` and `--renderer pygame` flag, (4) debug harness, (5) tests.

**Prompt:** "Review the plan."

**Response:** Identified improvements: clearer texture strategy, better test coverage plan, wall-hit type tracking for textures.

**Prompt:** "Make the recommended revisions to the plan."

**Response:** Revised the plan with the recommended changes.

---

### 2. Implementation

**Prompt:** "OK — I approve the plan. Please implement."

**Response:** Implemented the full Pygame raycaster:
- **`gui/renderers/raycaster.py`** — Core DDA raycaster: casts one ray per screen column, tracks `RayHit` (distance, side, wall_x), renders vertical wall strips with distance-based height scaling, floor/ceiling with flat colors and distance fog
- **`gui/renderers/pygame_backend.py`** — `PygameBackend(BaseBackend)` wrapping the raycaster. Uses `pygame.Surface` rendered each frame via `QTimer`, converted to `QImage` for display in a `QLabel`
- Wired into `gui_main.py` and `main.py` with `--renderer pygame`
- Added backend test suite

---

### 3. Code Review and Fixes

**Prompt:** "Review the code."

**Response:** Found three issues: (1) player-position sync from snapshots not implemented (only `send_highlight_player` worked, not `send_maze_update`), (2) Pygame import fallback left a visible empty widget, (3) shutdown cleanup incomplete (potential SDL resource leak).

**Prompt:** "Can you fix the problems that you see."

**Response:** Fixed all three: added snapshot-driven player sync in `PygameBackend.send_maze_update()`, improved fallback layout when Pygame unavailable, and added proper cleanup in `stop()` (`pygame.quit()` and widget teardown). Added regression tests. 206 tests pass.

---

### 4. Godot Regression on Pygame Branch

**Prompt:** "The Godot engine is no longer working. Is that expected before merging all the branches?"

**Response:** Not expected. Found the `godot_debug_harness.py` still used old `MazeCanvas` internals that had moved to `GodotBackend` during the `BaseBackend` refactor. Fixed the harness.

**Prompt:** "The bug is 'waiting for Godot viewport' followed by 'Godot did not connect to bridge'."

**Response:** Traced the issue: `project.godot` was missing on this feature branch (it was only on `feat/gui-canvas` and `master`). Without it, Godot starts but never loads `main.tscn`, so the WebSocket client never initializes. Restored `project.godot` from commit `732873a`.

**Prompt:** "The connection is made but the walls are not drawn — we see a gray screen."

**Response:** Gray screen caused by `maze_builder.gd` failing to load because it preloads `texture_gen.gd` which was also missing on this branch. Restored `texture_gen.gd` from master.

**Prompt:** (User pasted Godot stderr showing `texture_gen.gd does not exist` and `get_cell_world_pos nonexistent`)

**Response:** Confirmed: restored both `texture_gen.gd` and verified all Godot project files were present.

---

### 5. Adding Textures

**Prompt:** "The Pygame does not have textures — is that normal?"

**Response:** Yes — the initial implementation used flat solid colors with distance fog (no bitmap/procedural textures). Offered to add procedural textures.

**Prompt:** "Yes that would be preferable."

**Response:** Switched to plan mode. Created a texture plan: procedural texture generation using NumPy arrays, `wall_x` tracking in `RayHit` for texture column mapping, per-pixel texture sampling for walls, textured floor/ceiling casting.

**Prompt:** "Implement the plan."

**Response:** Implemented the full texture system:
- **Texture generators** — `_gen_brick()`, `_gen_metal()`, `_gen_ceiling()`, `_gen_gate()`, `_gen_exit()`, `_gen_start()` using NumPy arrays (64x64 pixels each)
- **Wall textures** — Extended `RayHit` with `wall_x` (0.0–1.0 fractional hit position). Each screen column samples the correct texture column based on `wall_x`
- **Floor/ceiling textures** — Vectorized NumPy floor-casting: for each pixel below/above the horizon, cast a ray to the floor plane, compute world coordinates, sample the texture at those coordinates
- **Performance** — Used `numpy.surfarray.pixels3d` for direct surface manipulation, avoiding per-pixel Python loops
- Added `numpy>=1.24` to `requirements.txt`

---

### 6. Mirrored Wall Bug (Post-Merge)

**Prompt:** "Looking north the walls are mirrored image for Pygame."

**Response:** Found a sign error in the ray angle calculation in `raycaster.py`. The line:

```python
ray_angle = player_angle + math.atan2(camera_x * tan_half, 1.0)
```

Should have been:

```python
ray_angle = player_angle + math.atan2(-camera_x * tan_half, 1.0)
```

The positive `camera_x` cast rays to the right side of the screen but the angle calculation mapped them leftward, producing a horizontally mirrored view. The negation corrects the mapping.

---

## Key Files

| File | Purpose |
|------|---------|
| `gui/renderers/raycaster.py` | Core DDA raycaster — ray casting, wall/floor/ceiling rendering, texture sampling |
| `gui/renderers/pygame_backend.py` | `PygameBackend(BaseBackend)` — Pygame surface → QImage blitting |

## Rendering Architecture

```
PyQt6 MainWindow
  └── QLabel (viewport)
        └── PygameBackend
              ├── pygame.Surface (640x480)
              ├── QTimer (16ms) → render_frame() → blit to QLabel
              ├── DDA Raycaster (one ray per column)
              │     ├── Wall strips (textured, distance-scaled)
              │     ├── Floor casting (vectorized NumPy)
              │     └── Ceiling casting (vectorized NumPy)
              └── Procedural textures (NumPy arrays)
                    ├── Brick (walls)
                    ├── Metal (floor)
                    ├── Ceiling panels
                    ├── Gate barrier
                    ├── Exit portal
                    └── Start marker
```

## Lessons Learned

1. **NumPy is essential for Python raycasting** — Per-pixel Python loops are too slow; vectorized `surfarray.pixels3d` makes 640x480 real-time rendering feasible.
2. **Sign conventions matter** — A single sign error in `atan2` mirrors the entire world. Easy to miss visually when there's no obvious asymmetry.
3. **Branch file dependencies** — Godot files (`project.godot`, `texture_gen.gd`) missing on the Pygame branch caused silent Godot failures. Always verify cross-renderer files when branching.
4. **Flat colors first, textures second** — Getting the geometry and DDA algorithm correct with flat colors first, then layering textures on top, was a clean separation of concerns.
