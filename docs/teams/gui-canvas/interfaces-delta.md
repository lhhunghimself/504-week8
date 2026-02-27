# GUI Canvas Team (Team 2) — Interfaces Delta

Additions to `interfaces.md` owned by the GUI Canvas team.
Target branch: `feat/gui-canvas`

---

## Data Contract

The canvas consumes `MazeSnapshot` (see `interfaces.md` Section 7.2):

```
MazeSnapshot
  width: int
  height: int
  cells: list[CellView]  (row-major, width * height items)

CellView
  row: int
  col: int
  kind: str          "start" | "exit" | "normal"
  visible: bool      False = fog of war
  is_player: bool
  has_gate: bool     unsolved gate present
  solved: bool       gate was solved
  connections: list[str]  open directions: ["N", "E", ...]
```

The canvas does NOT import `maze.py` directly. All maze data arrives pre-processed via `MazeSnapshot`.

---

## Widget Contract

### MazeCanvas (QWidget)

Signals:
- `direction_clicked(str)`: emitted when user clicks an adjacent cell. Value is "N", "S", "E", or "W".

Slots:
- `update_maze(MazeSnapshot)`: full or incremental maze redraw. Canvas should diff internally and redraw only changed cells.
- `highlight_player(tuple[int,int])`: animate player position to `(row, col)`.

Required query methods (for testing):
- `cell_count() -> int`: number of rendered cells
- `cell_style(row, col) -> str`: style identifier for the cell (for asserting fog vs visible)
- `has_player_indicator(row, col) -> bool`: whether cell shows player marker
- `has_gate_indicator(row, col) -> bool`: whether cell shows gate marker
- `has_connection(row, col, direction) -> bool`: whether cell has a passage drawn in the given direction
- `click_cell(row, col)`: programmatic click on a cell (for testing)
- `last_update_changed_cells() -> list[tuple[int,int]]`: cells redrawn in the most recent `update_maze` call

---

## Canvas Toolkit

The rendering technology (QGraphicsScene, QPainter, etc.) is an internal implementation detail. The only hard requirement is that the canvas is embeddable as a `QWidget` in the main window layout.

---

## Test Coverage

| Test ID | Test Name | Status |
|---|---|---|
| F.1 | `test_canvas_renders_correct_cell_count` | pending |
| F.2 | `test_fog_cells_rendered_differently` | pending |
| F.3 | `test_player_cell_highlighted` | pending |
| F.4 | `test_gate_cell_marked` | pending |
| F.5 | `test_connections_drawn` | pending |
| F.6 | `test_click_adjacent_cell_emits_direction` | pending |
| F.7 | `test_update_redraws_only_changed_cells` | pending |
| F.8 | `test_canvas_handles_variable_sizes` | pending |
