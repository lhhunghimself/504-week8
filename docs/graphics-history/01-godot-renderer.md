# Godot 4 Renderer — Development History

**Branch:** `feat/gui-canvas` (Godot WebSocket bridge + 2D canvas)
**Debug branch:** `debug/godot-draw-harness`
**Key commits:** `732873a`, `bedee2f`, `4fa2e9b`, `505043a`
**Date:** 2026-02-27

---

## Context

The Godot renderer was the first 3D backend attempted. The idea: run Godot 4 as an external process communicating with the PyQt6 GUI over a WebSocket bridge. Godot handles 3D rendering (Camera3D, OmniLight3D, StandardMaterial3D), while PyQt manages game state, forms, and the 2D minimap.

---

## Play-by-Play

### 1. Initial Canvas + Godot Integration

**Prompt:** "Read the handoff document. I am getting 'GUI not available. Install PyQt6 and ensure gui_main.py exists.' but PyQt6 is installed."

**Response:** The `gui_main.py` file existed only on feature branches (`feat/gui-controller`, `feat/gui-forms`, `feat/gui-canvas`) that hadn't been merged to master yet. Merged the three GUI branches into master in order: controller → forms → canvas. Fixed a PySide6/PyQt6 import conflict. 136 tests pass.

---

### 2. Godot Not Rendering

**Prompt:** "Review the code. Godot graphics is not showing up."

**Response:** Identified issues in the Godot integration: spawn position bug, process fallback behavior, missing `--no-godot` CLI wiring, and dependency gaps (`PyQt6-WebSockets` not in requirements). Catalogued them by severity.

---

### 3. Window Appearing Then Disappearing

**Prompt:** "I am seeing the window and then it is disappearing. Make the fixes and then if it fails we will try a new debug branch and set up a harness."

**Response:** Implemented four fixes: hardened Godot process fallback (graceful degradation when Godot exits), fixed initial player spawn coordinates in `player.gd`, wired `--no-godot` flag through `main.py` to `gui_main.py`, and added `PyQt6-WebSockets` to `requirements.txt`.

---

### 4. Window Opens But Nothing Drawn

**Prompt:** "The window appears but nothing is drawn."

**Response:** Inspected the full Godot rendering pipeline — `main.tscn`, `maze_builder.gd`, `ws_client.gd`, `crt_shader.gdshader` — looking for why the connected Godot process showed a blank viewport.

---

### 5. Branching Off to Debug Systematically

**Prompt:** "No, branch off a new debug branch and let's start systematically debugging this. Create a test harness which just feeds the engine a view and let's confirm that this is drawn in the Godot window."

**Response:** Created `debug/godot-draw-harness` branch. Built `godot_debug_harness.py` — a standalone script that boots a minimal game engine, gets `engine.view().maze_snapshot`, and sends it directly to `MazeCanvas` for Godot rendering. This isolates the rendering from the full game loop.

---

### 6. Black Screen Diagnosis

**Prompt:** "The screen is black, not blank. On exit I get Godot connected then 'Godot exited (code=0, status=NormalExit)'."

**Response:** Root cause: `MazeCanvas` used a single-string buffer for pre-connection messages, so when both `maze_update` and `highlight_player` were sent before Godot connected, the first message was overwritten. **Fix:** Changed the pre-connection buffer from a single string to a FIFO queue so all messages are preserved. Also adjusted camera position, lighting intensity, and CRT overlay opacity.

---

### 7. Automated Angle Sweep Testing

**Prompt:** "The view now displays. Go through the maze and display all possible angles at each position and ensure no errors in Godot."

**Response:** Added an automated sweep mode to the harness: traverses every reachable cell, rotates through all 4 compass headings at each position, and reports any Godot errors. Extended the WebSocket bridge with a `set_view_direction` message type. Updated `player.gd` to handle facing changes independently of movement. Sweep passed: 50 actions, 0 errors.

---

### 8. What Was Actually Fixed

**Prompt:** "This worked very well. What did you fix in order for the display to show the correct scenes?"

**Response:** The key fix was the FIFO message queue in `MazeCanvas` (replacing a single-overwrite buffer). Secondary fixes: resolved Godot compile blockers (`texture_gen.gd` preload path, `player.gd` typing errors, shader return value), corrected camera spawn and orientation, tuned cell visibility radius, and hardened the WebSocket bridge protocol.

---

### 9. Manual Testing with Minimal Maze

**Prompt:** "OK can we try the changes now, using a minimal maze."

**Response:** Ran the harness with `--size 3 --seed 0 --gates 1 --sweep-angles`. SWEEP PASS — 50 actions, no Godot errors.

**Prompt:** "OK now let's do this manually."

**Response:** Launched the harness in manual mode with controls: Q/E for rotation, W/A/S/D for movement.

**Prompt:** "The turn works but not the move forward or move backward."

**Response:** The `MazeCanvas.direction_clicked` signal was not connected to the harness movement handler. Wired the signal connection.

---

### 10. Integration with Full Game

**Prompt:** "This seems to work, can we now hook this up to the full game with a PyQt6 main window?"

**Response:** Wired the Godot bridge into the full `MainWindow` path. Validated with a smoke test that emitting a canvas movement signal advances the engine position correctly.

**Prompt:** "This works, but the 2D map is not showing up in the QT window."

**Response:** The `MazeCanvas.paintEvent` had an early return that blocked 2D drawing when Godot was active. Removed the guard so the 2D minimap renders alongside the 3D Godot view.

---

### 11. Embedding Godot Inside PyQt

**Prompt:** "Is it possible to have the Godot window as part of the PyQt6 layout?"

**Response:** Yes, on X11 via Godot's `--wid <window_id>` flag. Implemented a native Qt host widget that passes its `winId()` to Godot for X11 window embedding, with fallback to a separate window on failure.

**Prompt:** "The internal widget for Godot is black and Godot never draws to it."

**Response:** Improved the embed handshake: wait for a valid native host window before launching, use X11-specific flags (`--wid`, `--single-window`, `--display-driver x11`, `--rendering-driver opengl3`), and add retry logic.

**Prompt:** "Still black."

**Response:** Tried reparenting Godot into the Qt host after it creates its own window (instead of at startup). Added debug logging.

**Prompt:** "Initially when the window shows up there is nothing. However if I expand the window to its full size, the Godot window kicks in. I'm thinking it's an initialization timing thing."

**Response:** Diagnosed as a race condition between Qt layout and Godot's initial render. **Fix:** Added a forced refresh kick sequence at 0ms, 80ms, 220ms, and 500ms after embedding — each syncs geometry, updates/repaints, and nudges the Godot window. Also added `eventFilter` hooks on Show/Resize/WindowStateChange to trigger geometry syncs on host resize.

---

### 12. Facing Indicators and Minimap Overlay

**Prompt:** "Commit. But we need facing text, a direction arrow in the 2D maze, and can the 2D maze be rendered in Godot as well?"

**Response:** Implemented all three: facing text label in PyQt status area, direction arrow drawn on the 2D minimap, and a Godot-side minimap overlay via `CanvasLayer` and `minimap.gd`. Added `facing_changed` signal flow from Godot through the bridge to PyQt.

**Prompt:** "Facing only updates after you move. Should update when facing changes."

**Response:** Patched `player.gd` so facing is emitted on turn (Q/E key press), not only after movement-triggered updates.

---

## Key Files

| File | Purpose |
|------|---------|
| `gui/maze_canvas.py` | MazeCanvas widget — QPainter 2D grid + WebSocket bridge to Godot |
| `godot_maze/project.godot` | Godot project configuration |
| `godot_maze/scripts/maze_builder.gd` | Builds 3D maze geometry from bridge messages |
| `godot_maze/scripts/player.gd` | Camera, movement, facing in Godot |
| `godot_maze/scripts/ws_client.gd` | WebSocket client connecting to PyQt bridge |
| `godot_maze/scripts/texture_gen.gd` | Procedural PBR texture generation |
| `godot_maze/scripts/minimap.gd` | Godot-side minimap CanvasLayer overlay |
| `godot_debug_harness.py` | Standalone debug harness for isolated testing |

## Rendering Architecture

```
PyQt6 MainWindow
  ├── MazeCanvas (QPainter 2D minimap)
  │     └── WebSocket Server (port auto)
  └── Native Host Widget (X11 embed)
        └── Godot 4 Process
              ├── ws_client.gd → connects to WebSocket
              ├── maze_builder.gd → builds 3D geometry
              ├── player.gd → Camera3D + OmniLight3D
              └── texture_gen.gd → StandardMaterial3D textures
```

## Lessons Learned

1. **Message buffering matters** — A single-overwrite buffer lost critical `maze_update` messages before Godot connected. FIFO queue solved it.
2. **X11 embedding is fragile** — Timing-dependent; required a multi-stage kick sequence with escalating delays.
3. **External process = external state** — Every Godot script error is invisible to Python; stderr logging and the debug harness were essential for diagnosis.
4. **File dependencies across branches** — `texture_gen.gd` and `project.godot` missing on feature branches caused silent Godot failures (gray screen, no error in Python).
