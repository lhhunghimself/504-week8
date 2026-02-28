# Panda3D Renderer — Development History

**Branch:** `feat/gui-pygame-renderer` (originally `ursula`, then Panda3D work accumulated here)
**Key commits:** `5942432` through `557b79d`
**Date:** 2026-02-27

---

## Context

After Godot worked but required an external process, the goal was an in-process 3D renderer embedded directly in PyQt6. The user initially asked about "Ursina" (a Panda3D wrapper), which led to implementing a native Panda3D backend using `ShowBase` running inside the same Python process. This also motivated creating the `BaseBackend` abstraction layer so multiple renderers could coexist.

---

## Play-by-Play

### 1. Exploring Ursina / Panda3D

**Prompt:** "Branch off a new ursula branch from main. I would like to implement something similar using ursula."

**Response:** Created `ursula` branch from `origin/master`. Clarified that "ursula" likely means Ursina (a Python game engine built on Panda3D).

**Prompt:** "Yes, plan out how we would implement the same interface and similar graphics using ursula instead of Godot."

**Response:** Researched Ursina/Panda3D embedding options. Since Ursina's `ShowBase` is actually Panda3D under the hood, proposed using Panda3D directly for more control over the Qt embedding. Drafted a multi-phase plan.

**Prompt:** "Roll this out into a full plan first that we can iterate on."

**Response:** Created a detailed plan with phases: cherry-pick GUI baseline from `debug/godot-draw-harness`, create `BaseBackend` abstraction, implement `PandaBackend` with `ShowBase`, add visual parity (textures, lighting), debug harness, tests, and CLI `--renderer` flag.

---

### 2. Full Implementation

**Prompt:** "Implement the plan as specified. Don't stop until you have completed all the to-dos."

**Response:** Executed all six phases:
- **Phase 0:** Cherry-picked GUI baseline from `debug/godot-draw-harness` with conflict resolution
- **Phase 1:** Created `panda3d_embed_spike.py` feasibility spike — proved `ShowBase` can be driven by `QTimer` calling `taskMgr.step()` each frame
- **Phase 2:** Extracted `gui/renderers/base_backend.py` (abstract `BaseBackend`) and `godot_backend.py` (extracted from `MazeCanvas`)
- **Phase 3:** Implemented `panda3d_backend.py` — `ShowBase` embedded in a native Qt widget via `makeDefaultPipe()` and `openWindow()` with the widget's `winId()`
- **Phase 4:** Added procedural textures (brick, metal floor, ceiling) and in-viewport minimap overlay
- **Phase 5:** Created `panda3d_debug_harness.py` with sweep testing and backend test suite
- **Phase 6:** Added `--renderer {godot,panda3d}` CLI flag and updated docs

158 tests passing after implementation.

---

### 3. Code Review

**Prompt:** "Review the new code for correctness, test compliance, and whether the plan has been executed."

**Response:** Found four issues: (1) Panda3D resize handling not wired through `installEventFilter`, (2) missing resize regression test, (3) outdated CLI usage string, (4) `--no-godot` vs `--renderer` flag parsing was order-dependent. All addressed in next step.

**Prompt:** "Yes please fix these issues."

**Response:** Fixed Panda3D viewport resize event filtering, added regression test, made CLI flag handling deterministic (`--renderer` always wins over `--no-godot`), updated usage text. 161 tests pass.

---

### 4. GLX Errors and Rendering Issues

**Prompt:** "The Ursina window draws something which I think is the 2D overlay, but the rest does not render. PyQt doesn't recognize arrow direction changes. Error on quit: GLXBadDrawable, BadMatch."

**Response:** Three fixes: (1) Deferred Panda3D startup until the viewport widget is actually shown (avoids GLX drawable errors on unmapped windows), (2) replayed buffered snapshot on start so walls appear immediately, (3) added arrow-key turning injection through `MazeCanvas` and `MainWindow` key events.

**Prompt:** "Facing does not change — no walls rendered."

**Response:** Two root causes: (1) walls were invisible due to extremely dark material colors and narrow 30° FOV — brightened wall materials, increased ambient light, widened FOV to 75°; (2) keyboard input wasn't reaching the embedded Panda3D widget — added `inject_key` method on `BaseBackend`, wired `keyPressEvent`/`keyReleaseEvent` on `MazeCanvas` and `MainWindow`, set `StrongFocus` policy. Fixed GLXBadDrawable on quit by deactivating the graphics window and calling `removeWindow()` before `destroy()`.

---

### 5. Viewport Sizing Problems

**Prompt:** "It now draws but doesn't take up the whole window — just basic filled shapes, no textures."

**Response:** Found `_viewport_host` had an empty layout causing size collapse. Set `sizePolicy` to Expanding and adjusted splitter stretch factors. Added procedural texture generators (brick, metal, ceiling) and applied them via `setTexture()`.

**Prompt:** "It's just that the current Ursina window only has graphics taking up the top-left 70% of the window."

**Response:** Panda3D was reading widget size before Qt layout was finalized. Added `showEvent` deferral and staggered resize syncs at 50ms, 150ms, 300ms, 600ms. Added `requestProperties` flush with inline `taskMgr.step()` calls.

**Prompt:** "Better — it's playable but the graphics don't take up the entire viewport."

**Response:** Size mismatch due to HiDPI: Qt reports logical pixels but Panda3D needs physical pixels. Added `_host_pixel_size()` using `devicePixelRatioF()` for correct physical pixel dimensions.

**Prompt:** "I tried resizing, it doesn't fix itself. The textures are nicer but the viewport size is still a problem — it's not the full left panel, it's the viewport in the upper right."

**Response:** Applied device-pixel-ratio scaling throughout: startup, resize handler, and size comparison. Added exponential back-off polling until Panda3D and Qt sizes converge.

---

### 6. Direction Mapping Fix

**Prompt:** "The viewport is fixed but the directions being viewed are off — a N view is an East view I think."

**Response:** Corrected compass-to-Panda3D heading mapping. Panda3D uses a different coordinate system (Y-forward, Z-up with heading measured from Y-axis). Fixed `_FACING_TO_H` and `_H_TO_FACING` lookup tables so N→+Y and E→+X. Fixed turn logic so left/right match Panda3D heading convention.

---

## Key Files

| File | Purpose |
|------|---------|
| `gui/renderers/base_backend.py` | Abstract `BaseBackend` interface (created for Panda3D) |
| `gui/renderers/panda3d_backend.py` | Panda3D in-process renderer via `ShowBase` |
| `gui/renderers/godot_backend.py` | Godot backend extracted to `BaseBackend` subclass |
| `panda3d_embed_spike.py` | Feasibility spike — proof that `QTimer` + `taskMgr.step()` works |
| `panda3d_debug_harness.py` | Standalone debug harness with sweep testing |

## Rendering Architecture

```
PyQt6 MainWindow
  ├── Native Host Widget (winId() passed to Panda3D)
  │     └── ShowBase (in-process)
  │           ├── taskMgr.step() driven by QTimer (16ms)
  │           ├── Procedural 3D geometry (walls, floor, ceiling)
  │           ├── Procedural textures (brick, metal, ceiling)
  │           └── Minimap overlay (OnscreenImage + OnscreenText)
  └── MazeCanvas (2D minimap, still works alongside)
```

## Key Architectural Decision: BaseBackend

The Panda3D work motivated creating `BaseBackend` — an abstract class that all renderers implement:

```python
class BaseBackend:
    def start(self, parent_widget): ...
    def stop(self): ...
    def is_ready(self) -> bool: ...
    def send_maze_update(self, snapshot_dict): ...
    def send_highlight_player(self, row, col): ...
    def send_view_direction(self, direction): ...
    def inject_key(self, key_name, *, pressed): ...
```

This abstraction enabled `--renderer {godot,panda3d,pygame,qpaint}` switching and made all subsequent backends straightforward to add.

## Lessons Learned

1. **In-process beats external** — No WebSocket overhead, no startup race conditions, no separate process to manage.
2. **HiDPI is a trap** — Qt reports logical pixels, Panda3D needs physical pixels. `devicePixelRatioF()` is essential.
3. **Deferred initialization required** — Panda3D must not open a window until the Qt host widget is mapped and has a real size. Staggered timer syncs handle the layout race.
4. **Coordinate system mapping** — Panda3D heading conventions differ from compass directions. A simple lookup table fix, but hard to notice visually (N looks like E).
