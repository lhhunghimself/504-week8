"""F-series: Maze Canvas widget contract tests.

Tests validate Team 2's canvas widget in isolation using hardcoded MazeSnapshot objects.
No engine, DB, or maze.py imports needed.
Skipped entirely if PyQt6 is not installed.
"""
import importlib

import pytest

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("PyQt6"),
    reason="PyQt6 not installed — skipping GUI canvas tests",
)


# ---------------------------------------------------------------------------
# Snapshot factory helpers
# ---------------------------------------------------------------------------

def _make_cell(row, col, *, kind="normal", visible=True, is_player=False,
               has_gate=False, solved=False, connections=None):
    main = importlib.import_module("main")
    return main.CellView(
        row=row, col=col, kind=kind, visible=visible,
        is_player=is_player, has_gate=has_gate, solved=solved,
        connections=connections or [],
    )


def _make_snapshot(width, height, overrides=None):
    """Build a simple MazeSnapshot with optional cell overrides."""
    main = importlib.import_module("main")
    cells = []
    override_map = {(c.row, c.col): c for c in (overrides or [])}
    for r in range(height):
        for c in range(width):
            if (r, c) in override_map:
                cells.append(override_map[(r, c)])
            else:
                cells.append(_make_cell(r, c, visible=(r == 0 and c == 0)))
    return main.MazeSnapshot(width=width, height=height, cells=cells)


@pytest.fixture
def snapshot_3x3():
    """3x3 snapshot: player at (0,0), fog everywhere else."""
    return _make_snapshot(3, 3, overrides=[
        _make_cell(0, 0, kind="start", visible=True, is_player=True, connections=["E", "S"]),
    ])


@pytest.fixture
def snapshot_with_gate():
    """3x3 snapshot with a gate cell at (0,2)."""
    return _make_snapshot(3, 3, overrides=[
        _make_cell(0, 0, kind="start", visible=True, is_player=True, connections=["E"]),
        _make_cell(0, 1, visible=True, connections=["E", "W"]),
        _make_cell(0, 2, visible=True, has_gate=True, connections=["W"]),
    ])


# ---------------------------------------------------------------------------
# F.1 — Canvas renders correct cell count
# ---------------------------------------------------------------------------

def test_canvas_renders_correct_cell_count(qtbot, snapshot_3x3):
    from gui.maze_canvas import MazeCanvas

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot_3x3)

    assert canvas.cell_count() == 9


# ---------------------------------------------------------------------------
# F.2 — Fog cells rendered differently
# ---------------------------------------------------------------------------

def test_fog_cells_rendered_differently(qtbot, snapshot_3x3):
    from gui.maze_canvas import MazeCanvas

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot_3x3)

    visible_style = canvas.cell_style(0, 0)
    fog_style = canvas.cell_style(1, 1)
    assert visible_style != fog_style, "fog and visible cells must have distinct styles"


# ---------------------------------------------------------------------------
# F.3 — Player cell highlighted
# ---------------------------------------------------------------------------

def test_player_cell_highlighted(qtbot, snapshot_3x3):
    from gui.maze_canvas import MazeCanvas

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot_3x3)

    assert canvas.has_player_indicator(0, 0)


# ---------------------------------------------------------------------------
# F.4 — Gate cell marked
# ---------------------------------------------------------------------------

def test_gate_cell_marked(qtbot, snapshot_with_gate):
    from gui.maze_canvas import MazeCanvas

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot_with_gate)

    assert canvas.has_gate_indicator(0, 2)


# ---------------------------------------------------------------------------
# F.5 — Connections drawn
# ---------------------------------------------------------------------------

def test_connections_drawn(qtbot, snapshot_3x3):
    from gui.maze_canvas import MazeCanvas

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot_3x3)

    assert canvas.has_connection(0, 0, "E"), "start cell should have an east connection drawn"


# ---------------------------------------------------------------------------
# F.6 — Click adjacent cell emits direction
# ---------------------------------------------------------------------------

def test_click_adjacent_cell_emits_direction(qtbot):
    from gui.maze_canvas import MazeCanvas

    snapshot = _make_snapshot(3, 3, overrides=[
        _make_cell(0, 0, visible=True, connections=["E", "S"]),
        _make_cell(0, 1, visible=True, connections=["W"]),
        _make_cell(1, 0, visible=True, connections=["N"]),
        _make_cell(1, 1, kind="normal", visible=True, is_player=True, connections=["N", "W"]),
    ])

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot)

    with qtbot.waitSignal(canvas.direction_clicked, timeout=1000) as sig:
        canvas.click_cell(0, 1)  # cell north of player at (1,1)
    assert sig.args == ["N"]


# ---------------------------------------------------------------------------
# F.7 — Update redraws only changed cells
# ---------------------------------------------------------------------------

def test_update_redraws_only_changed_cells(qtbot, snapshot_3x3):
    from gui.maze_canvas import MazeCanvas

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot_3x3)

    snap2 = _make_snapshot(3, 3, overrides=[
        _make_cell(0, 0, kind="start", visible=True, connections=["E", "S"]),
        _make_cell(0, 1, visible=True, is_player=True, connections=["E", "W"]),
    ])
    canvas.update_maze(snap2)

    changed = canvas.last_update_changed_cells()
    assert len(changed) >= 1, "at least 1 cell should have been redrawn"
    assert len(changed) < 9, "should not redraw all cells on a 1-cell change"


# ---------------------------------------------------------------------------
# F.8 — Canvas handles variable sizes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size", [3, 5, 7])
def test_canvas_handles_variable_sizes(qtbot, size):
    from gui.maze_canvas import MazeCanvas

    snapshot = _make_snapshot(size, size, overrides=[
        _make_cell(0, 0, kind="start", visible=True, is_player=True),
    ])

    canvas = MazeCanvas()
    qtbot.addWidget(canvas)
    canvas.update_maze(snapshot)

    assert canvas.cell_count() == size * size
