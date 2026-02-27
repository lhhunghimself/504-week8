"""D-series: GUI contract tests (no Qt dependency).

Validates MazeSnapshot / CellView data contracts and the engine-to-GUI boundary.
Uses the real engine with a test maze and repo.
"""
import importlib

import pytest


def _import_required(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        pytest.fail(f"Required module '{name}.py' not found. Original error: {e}")


def _make_engine(maze_module, repo, puzzle_registry, *, maze=None):
    main = _import_required("main")
    engine_cls = getattr(main, "GameEngine")
    cmd_cls = getattr(main, "Command")

    if maze is None:
        maze = maze_module.build_minimal_3x3_maze()

    player = repo.get_or_create_player("neo")
    player_id = player["id"] if isinstance(player, dict) else player.id

    initial_state = {
        "pos": {"row": maze.start.row, "col": maze.start.col},
        "move_count": 0,
        "solved_gates": [],
        "started_at": "2026-02-13T00:00:00Z",
        "visited": [{"row": maze.start.row, "col": maze.start.col}],
        "hints_used": 0,
        "maze_size": maze.width,
        "num_gates": 1,
        "maze_seed": 0,
    }
    game = repo.create_game(
        player_id=player_id,
        maze_id=maze.maze_id,
        maze_version=maze.maze_version,
        initial_state=initial_state,
    )
    game_id = game["id"] if isinstance(game, dict) else game.id

    engine = engine_cls(
        maze=maze, repo=repo, puzzles=puzzle_registry,
        player_id=player_id, game_id=game_id,
    )
    return engine, cmd_cls, maze


def _dir_token(d) -> str:
    return d.name


def _trigger_pending_puzzle(engine, cmd_cls, maze):
    """Move toward any gated direction to trigger a pending puzzle."""
    start_pos = maze.start
    for d in maze.available_moves(start_pos):
        gate_id = maze.gate_id_for(start_pos, d)
        if gate_id is not None:
            out = engine.handle(cmd_cls(verb="go", args=[_dir_token(d)]))
            if out.view.pending_puzzle is not None:
                return out
    return None


# ---------------------------------------------------------------------------
# D.1 — MazeSnapshot matches GameView
# ---------------------------------------------------------------------------

def test_maze_snapshot_matches_game_view(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze = _make_engine(maze_module, repo, puzzle_registry)
    view = engine.view()

    snap = view.maze_snapshot
    assert snap is not None, "maze_snapshot must be populated"
    assert len(snap.cells) == snap.width * snap.height
    assert snap.width == maze.width
    assert snap.height == maze.height

    player_cells = [c for c in snap.cells if c.is_player]
    assert len(player_cells) == 1, "exactly one cell should have is_player=True"
    assert player_cells[0].row == view.pos["row"]
    assert player_cells[0].col == view.pos["col"]

    unvisited = [c for c in snap.cells if not c.visible]
    assert len(unvisited) > 0, "fresh game should have fog-of-war hidden cells"


# ---------------------------------------------------------------------------
# D.2 — Snapshot updates after movement
# ---------------------------------------------------------------------------

def test_maze_snapshot_updates_after_movement(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze = _make_engine(maze_module, repo, puzzle_registry)

    snap_before = engine.view().maze_snapshot
    visible_before = {(c.row, c.col) for c in snap_before.cells if c.visible}

    for m in engine.view().available_moves:
        out = engine.handle(cmd_cls(verb="go", args=[m]))
        if out.view.pending_puzzle is not None:
            engine.handle(cmd_cls(verb="answer", args=["solve"]))
            out = engine.handle(cmd_cls(verb="go", args=[m]))
        if out.view.pos != {"row": maze.start.row, "col": maze.start.col}:
            break
    else:
        pytest.fail("Could not move from start even after solving gates")

    snap_after = out.view.maze_snapshot
    visible_after = {(c.row, c.col) for c in snap_after.cells if c.visible}
    assert visible_after > visible_before, "visible cells should increase after movement"


# ---------------------------------------------------------------------------
# D.3 — Gate status reflects solved state
# ---------------------------------------------------------------------------

def test_maze_snapshot_gate_status_reflects_solved(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze = _make_engine(maze_module, repo, puzzle_registry)
    out = _trigger_pending_puzzle(engine, cmd_cls, maze)

    if out is None:
        pytest.skip("No gated direction found from start")

    snap_before = out.view.maze_snapshot
    gate_cells_before = [c for c in snap_before.cells if c.has_gate]
    assert len(gate_cells_before) >= 1, "should have at least one unsolved gate cell"

    gate_cell = gate_cells_before[0]
    assert gate_cell.solved is False

    engine.handle(cmd_cls(verb="answer", args=["solve"]))
    snap_after = engine.view().maze_snapshot

    updated = next(
        c for c in snap_after.cells
        if c.row == gate_cell.row and c.col == gate_cell.col
    )
    assert updated.has_gate is False, "gate should no longer be unsolved"
    assert updated.solved is True, "gate should be marked solved"


# ---------------------------------------------------------------------------
# D.4 — CellView.kind matches maze cell kind
# ---------------------------------------------------------------------------

def test_cell_view_kind_matches_maze_cell_kind(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze = _make_engine(maze_module, repo, puzzle_registry)
    from maze import Position

    snap = engine.view().maze_snapshot
    for cv in snap.cells:
        cell = maze.cell(Position(row=cv.row, col=cv.col))
        assert cv.kind == cell.kind.value, (
            f"CellView kind '{cv.kind}' != maze kind '{cell.kind.value}' at ({cv.row},{cv.col})"
        )


# ---------------------------------------------------------------------------
# D.5 — Connections only on visible cells
# ---------------------------------------------------------------------------

def test_cell_view_connections_only_on_visible_cells(maze_module, repo, puzzle_registry):
    engine, cmd_cls, maze = _make_engine(maze_module, repo, puzzle_registry)

    snap = engine.view().maze_snapshot
    for cv in snap.cells:
        if not cv.visible:
            assert cv.connections == [], (
                f"Fog cell ({cv.row},{cv.col}) should have empty connections"
            )
        else:
            assert cv.connections == sorted(cv.connections), (
                f"Connections at ({cv.row},{cv.col}) should be sorted"
            )
