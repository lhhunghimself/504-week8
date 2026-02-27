# GUI Controller Team (Team 3) — Interfaces Delta

Additions to `interfaces.md` owned by the GUI Controller team.
Target branch: `feat/gui-controller`

---

## Changes to `main.py`

### New Dataclasses

- `CellView`: per-cell structured data for graphical rendering
- `MazeSnapshot`: collection of `CellView` items in row-major order
- `GameView.maze_snapshot: MazeSnapshot | None = None`: always populated by `_make_view()`

### New Startup Flag

- `StartupConfig.gui: bool = False`
- `--gui` flag in `_parse_startup_flags`
- When `gui=True`, `cli_main` delegates to `gui_main.gui_main(config)`

### New Helper

- `GameEngine._build_maze_snapshot() -> MazeSnapshot`: builds per-cell view data from current engine state

---

## New Files

### `gui/controller.py` — GameController

A `QObject` that bridges the engine to all GUI widgets.

Signals:
- `view_changed(GameView)`: broadcast after every engine response
- `messages_ready(list[str])`: engine messages for display
- `game_completed(dict)`: score metrics when game ends

Slots:
- `on_command(Command)`: receives commands from any widget, delegates to EngineWorker

Methods:
- `initialize()`: calls `engine.view()` and emits `view_changed` for initial state

### `gui/engine_worker.py` — EngineWorker

A `QThread` wrapper that runs `engine.handle(command)` off the main thread.

Signals:
- `result_ready(GameOutput)`: emitted when `engine.handle()` completes
- `error_occurred(str)`: emitted on unexpected engine error

Slots:
- `submit_command(Command)`: queued from the main thread

### `gui_main.py` — Entry Point

- Parses CLI flags (reuses `_parse_startup_flags` from `main.py`)
- Creates repo, maze, puzzles, engine (same as `cli_main`)
- Creates `QApplication`, `QMainWindow`
- Instantiates all Team 1 and Team 2 widgets
- Wires signals/slots via `GameController`
- Calls `controller.initialize()` to broadcast initial state

---

## Wiring Diagram

```
FormsPanel.command_issued  ──> GameController.on_command
MazeCanvas.direction_clicked ──> GameController.on_command (wrapped as Command)
PuzzleDialog.answer_submitted ──> GameController (wrapped as Command("answer", [text]))
PuzzleDialog.hint_requested  ──> GameController (wrapped as Command("hint", [type]))

GameController.on_command ──> EngineWorker.submit_command
EngineWorker.result_ready ──> GameController._handle_result

GameController.view_changed ──> FormsPanel.update_view
GameController.view_changed ──> MazeCanvas.update_maze (via snapshot)
GameController.view_changed ──> StatusBar.update_status
GameController.view_changed ──> PuzzleDialog.show_puzzle (via pending_puzzle)
GameController.messages_ready ──> FormsPanel.show_messages
GameController.game_completed ──> ScoreBoard.show_scores
```

---

## Test Coverage

| Test ID | Test Name | Status |
|---|---|---|
| D.1 | `test_maze_snapshot_matches_game_view` | passing |
| D.2 | `test_maze_snapshot_updates_after_movement` | passing |
| D.3 | `test_maze_snapshot_gate_status_reflects_solved` | passing |
| D.4 | `test_cell_view_kind_matches_maze_cell_kind` | passing |
| D.5 | `test_cell_view_connections_only_on_visible_cells` | passing |
| G.1 | `test_gui_startup_shows_initial_view` | pending (needs PyQt6) |
| G.2 | `test_direction_click_updates_both_panels` | pending (needs PyQt6) |
| G.3 | `test_puzzle_flow_through_gui` | pending (needs PyQt6) |
| G.4 | `test_hint_flow_through_gui` | pending (needs PyQt6) |
| G.5 | `test_game_completion_shows_score` | pending (needs PyQt6) |
| G.6 | `test_save_indicator_on_persist` | pending (needs PyQt6) |
